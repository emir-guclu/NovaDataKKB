import { Pool } from 'pg';

// PostgreSQL veritabanı bağlantı havuzu (Pool)
// Bu havuz, sohbet geçmişini ve LLM loglarını tutmak için kullanılacak.
const pool = new Pool({
  user: process.env.PG_USER || 'postgres',
  host: process.env.PG_HOST || 'localhost',
  database: process.env.PG_DATABASE || 'nova_agent_db',
  password: process.env.PG_PASSWORD || 'secret',
  port: parseInt(process.env.PG_PORT || '5432', 10),
});

// Ajanın konuşma geçmişini veritabanına kaydetme fonksiyonu taslağı
export const logChatToDB = async (userId: string, userMessage: string, aiResponse: string) => {
  try {
    const query = `
      INSERT INTO chat_logs (user_id, message, response, created_at)
      VALUES ($1, $2, $3, NOW())
      RETURNING id;
    `;
    const values = [userId, userMessage, aiResponse];
    const res = await pool.query(query, values);
    return res.rows[0].id;
  } catch (error) {
    console.error('Veritabanına log yazılırken hata oluştu:', error);
    // Hata fırlatmıyoruz ki loglama yüzünden asıl sistem çökmesin
    return null;
  }
};

export default pool;
