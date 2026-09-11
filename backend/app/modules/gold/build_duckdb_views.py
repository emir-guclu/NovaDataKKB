import duckdb
from pathlib import Path
import json
import sys

# Setup backend path for imports when run as script
_project_root = Path(__file__).parent.parent.parent.parent.parent
_backend_path = str(_project_root / "backend")
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

# Import the SQLAlchemy models
from app.models.lakehouse_models import lakehouse_metadata

def build_gold_duckdb_views(project_root: Path) -> None:
    """
    Builds the unified LLM-facing lakehouse.duckdb database.
    - Attaches Silver and Aligned databases as READ_ONLY
    - Creates Gold physical tables from Parquet
    - Registers EVDS catalog view
    - Builds the lakehouse_data_catalog table
    - Injects DuckDB native comments based on SQLAlchemy metadata
    """
    db_path = project_root / "data" / "lakehouse.duckdb"
    gold_dir = project_root / "data" / "gold"
    silver_db_path = project_root / "data" / "silver" / "silver.duckdb"
    aligned_db_path = project_root / "data" / "aligned" / "monthly" / "aligned.duckdb"
    evds_catalog_path = project_root / "data" / "bronze" / "evds" / "evds_catalog.parquet"
    
    print(f"Connecting to {db_path}...")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    
    # ========================================================
    # 1. ATTACH SILVER & ALIGNED DATABASES
    # ========================================================
    if silver_db_path.exists():
        print("Attaching silver.duckdb...")
        # Use execute to safely bind paths? ATTACH doesn't support bind params well, but path is internal
        # We ensure it's relative to project_root
        con.execute(f"ATTACH '{silver_db_path.as_posix()}' AS silver_db (READ_ONLY);")
        # Expose via view
        con.execute("CREATE OR REPLACE VIEW silver_observations AS SELECT * FROM silver_db.observations;")
        con.execute("CREATE OR REPLACE VIEW silver_series_metadata AS SELECT * FROM silver_db.series_metadata;")
    
    if aligned_db_path.exists():
        print("Attaching aligned.duckdb...")
        con.execute(f"ATTACH '{aligned_db_path.as_posix()}' AS aligned_db (READ_ONLY);")
        con.execute("CREATE OR REPLACE VIEW aligned_observations AS SELECT * FROM aligned_db.observations;")
        con.execute("CREATE OR REPLACE VIEW aligned_series_metadata AS SELECT * FROM aligned_db.series_metadata;")
        
    # ========================================================
    # 2. CREATE GOLD PHYSICAL TABLES & EVDS CATALOG VIEW
    # ========================================================
    gold_tables = [
        "gold_periodic_change",
        "gold_housing_credit_market",
        "gold_credit_market",
        "gold_deposit_market",
        "gold_precious_metal_ratios_daily",
        "gold_precious_metal_ratios_monthly",
        "gold_finturk_province_credit_quality",
        "gold_series_evidence"
    ]
    
    for table_name in gold_tables:
        parquet_file = gold_dir / f"{table_name}.parquet"
        if parquet_file.exists():
            print(f"Creating view for {table_name}...")
            # Safely replace view (drop any previous table/view to avoid type clash)
            try:
                con.execute(f"DROP TABLE IF EXISTS {table_name}")
            except Exception:
                pass
            con.execute(f"""
                CREATE OR REPLACE VIEW {table_name} AS 
                SELECT * FROM '{parquet_file.as_posix()}'
            """)
            
    if evds_catalog_path.exists():
        print("Creating view for gold_evds_catalog...")
        con.execute(f"""
            CREATE OR REPLACE VIEW gold_evds_catalog AS 
            SELECT * FROM '{evds_catalog_path.as_posix()}'
        """)
        
    # ========================================================
    # 3. BUILD LAKEHOUSE DATA CATALOG TABLE
    # ========================================================
    print("Building lakehouse_data_catalog physical table...")
    con.execute("DROP TABLE IF EXISTS lakehouse_data_catalog")
    con.execute("""
        CREATE TABLE lakehouse_data_catalog (
            table_name VARCHAR,
            layer VARCHAR,
            source_path VARCHAR,
            description VARCHAR
        )
    """)
    
    # Collect metadata for catalog
    catalog_entries = []
    
    # Add Silver/Aligned to catalog manually
    catalog_entries.extend([
        ('silver_observations', 'Silver', str(silver_db_path), 'Tüm raw (ham) veri kaynaklarının aynı formata dönüştürülmüş tablosu'),
        ('silver_series_metadata', 'Silver', str(silver_db_path), 'Silver serilerinin metadata bilgileri'),
        ('aligned_observations', 'Aligned', str(aligned_db_path), 'Aylık frekansa hizalanmış ve interpolation yapılmış çekirdek veri tablosu'),
        ('aligned_series_metadata', 'Aligned', str(aligned_db_path), 'Hizalanmış serilerin metadata bilgileri'),
        ('gold_evds_catalog', 'Bronze', str(evds_catalog_path), 'Agent keşfi için EVDS sistemindeki tüm kategorilerin ve serilerin meta tablosu')
    ])
    
    # Add Gold from SQLAlchemy models
    for table_name, table_obj in lakehouse_metadata.tables.items():
        if table_name == 'lakehouse_data_catalog':
            continue
        parquet_path = str(gold_dir / f"{table_name}.parquet")
        desc = table_obj.comment or ""
        catalog_entries.append((table_name, 'Gold', parquet_path, desc))
        
    # Insert into duckdb catalog
    for entry in catalog_entries:
        con.execute("INSERT INTO lakehouse_data_catalog VALUES (?, ?, ?, ?)", entry)
        
    # ========================================================
    # 4. INJECT NATIVE DUCKDB COMMENTS (from SQLAlchemy schema)
    # ========================================================
    print("Injecting native DuckDB comments from SQLAlchemy metadata...")
    for table_name, table_obj in lakehouse_metadata.tables.items():
        # Check if table exists in DuckDB (some might not have parquets available yet)
        table_exists = con.execute(f"SELECT COUNT(*) FROM sqlite_master WHERE name = '{table_name}'").fetchone()[0] > 0
        if not table_exists:
            continue
            
        if table_obj.comment:
            # Safely escape single quotes for SQL
            safe_comment = table_obj.comment.replace("'", "''")
            try:
                con.execute(f"COMMENT ON TABLE {table_name} IS '{safe_comment}'")
            except Exception:
                try:
                    con.execute(f"COMMENT ON VIEW {table_name} IS '{safe_comment}'")
                except Exception:
                    pass
            
        for col in table_obj.columns:
            if col.comment:
                safe_comment = col.comment.replace("'", "''")
                try:
                    con.execute(f"COMMENT ON COLUMN {table_name}.{col.name} IS '{safe_comment}'")
                except Exception:
                    pass

    con.close()
    print("Lakehouse successfully built with Native Catalog & Attached DBs.")

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent.parent.parent
    
    import sys
    # Add backend/ to Python path so we can import app.models
    backend_path = str(project_root / "backend")
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
        
    build_gold_duckdb_views(project_root)
