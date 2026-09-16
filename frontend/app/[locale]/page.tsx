"use client";

import { signIn, signOut, useSession } from "next-auth/react";
import { SessionProvider } from "next-auth/react";
import { useTranslations } from 'next-intl';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';

function DashboardContent({ t }: { t: any }) {
  const { data: session } = useSession();
  
  // Hydration hatasını önlemek için state'i önce false başlatıp,
  // sayfa yüklendikten (useEffect) sonra localStorage'dan okuyoruz.
  const [devMode, setDevMode] = useState(false);

  // Mesajlaşma State'leri
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Array<{ role: string; content: string }>>([
    { role: "agent", content: "" } // İçerik boş, aşağıda t() ile doldurulacak
  ]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const isDev = localStorage.getItem('devMode') === 'true';
      if (isDev) setDevMode(true);

      const savedChat = sessionStorage.getItem('nova_chat_messages');
      if (savedChat) {
        try {
          const parsed = JSON.parse(savedChat);
          if (Array.isArray(parsed) && parsed.length > 0) {
            setMessages(parsed);
          }
        } catch (e) {
          console.error("Failed to load chat from sessionStorage", e);
        }
      }
    }
  }, []);

  // Mesajlar değiştikçe sessionStorage'a kaydet
  useEffect(() => {
    if (typeof window !== 'undefined') {
      if (messages.length > 1 || (messages.length === 1 && messages[0].content !== "")) {
        sessionStorage.setItem('nova_chat_messages', JSON.stringify(messages));
      }
    }
  }, [messages]);

  const clearChat = () => {
    if (typeof window !== 'undefined') {
      sessionStorage.removeItem('nova_chat_messages');
    }
    setMessages([{ role: "agent", content: "" }]);
  };

  const toggleDevMode = (val: boolean) => {
    setDevMode(val);
    if (val) localStorage.setItem('devMode', 'true');
    else localStorage.removeItem('devMode');
  };

  const isLoggedIn = session || devMode;

  const handleSend = async () => {
    if (!input.trim()) return;
    
    const userMsg = input;
    setMessages(prev => [...prev, { role: "user", content: userMsg }]);
    setInput("");
    setIsLoading(true);

    try {
      // Backend'e istek atıyoruz
      const response = await fetch("http://localhost:8000/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: userMsg })
      });
      
      const data = await response.json();
      setMessages(prev => [...prev, { role: "agent", content: data.answer }]);
    } catch (error) {
      setMessages(prev => [...prev, { role: "agent", content: "Hata: Sunucuya bağlanılamadı. Backend açık mı?" }]);
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoggedIn) {
    return (
      <div className="flex h-full w-full bg-[#050505] text-gray-200 font-sans overflow-hidden selection:bg-blue-500/30">
        {/* Arka Plan Efektleri */}
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-blue-900/20 blur-[120px] pointer-events-none"></div>
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-emerald-900/10 blur-[120px] pointer-events-none"></div>

        {/* Sol Panel - Chat */}
        <div className="relative w-full md:w-[400px] lg:w-[450px] flex flex-col border-r border-white/5 bg-white/[0.02] backdrop-blur-2xl z-10 shadow-2xl">
          
          {/* Header */}
          <div className="px-6 py-5 border-b border-white/5 flex justify-between items-center bg-black/20">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-500 to-emerald-400 flex items-center justify-center shadow-lg shadow-blue-500/20">
                <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
              </div>
              <h2 className="text-xl font-black bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-400 tracking-tight">{t('chat_title')}</h2>
            </div>
            <div className="flex gap-2 text-xs font-semibold items-center">
              <button 
                onClick={clearChat}
                className="px-2 py-1 bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white rounded-md border border-white/5 transition-all flex items-center gap-1"
                title="Sohbeti Temizle"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                <span className="hidden sm:inline">Temizle</span>
              </button>
              <Link href="/tr" className="px-2.5 py-1.5 bg-white/5 rounded-md hover:bg-white/10 border border-white/5 transition-all">TR</Link>
              <Link href="/en" className="px-2.5 py-1.5 bg-white/5 rounded-md hover:bg-white/10 border border-white/5 transition-all">EN</Link>
              <button 
                onClick={() => {
                  if (typeof window !== 'undefined') sessionStorage.removeItem('nova_chat_messages');
                  devMode ? toggleDevMode(false) : signOut();
                }} 
                className="px-2.5 py-1.5 text-red-400 hover:text-white hover:bg-red-500/80 rounded-md transition-all ml-1"
                title={t('logout_button')}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
              </button>
            </div>
          </div>

          {/* Mesajlaşma Alanı */}
          <div className="flex-1 p-6 overflow-y-auto space-y-6 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-thumb]:rounded-full">
            {messages.map((msg, idx) => (
              <div key={idx} className={`flex flex-col ${msg.role === "agent" ? "items-start" : "items-end"} group`}>
                <div className={`flex items-end gap-2 max-w-[85%] ${msg.role === "agent" ? "flex-row" : "flex-row-reverse"}`}>
                  
                  {/* Avatar */}
                  {msg.role === "agent" ? (
                    <div className="w-7 h-7 rounded-full bg-gradient-to-br from-emerald-400 to-teal-600 flex-shrink-0 flex items-center justify-center shadow-lg shadow-emerald-500/20 mb-1">
                      <span className="text-[10px] font-black text-white">N</span>
                    </div>
                  ) : (
                    <div className="w-7 h-7 rounded-full bg-gradient-to-br from-gray-600 to-gray-800 flex-shrink-0 flex items-center justify-center shadow-lg mb-1 border border-white/10">
                      <svg className="w-4 h-4 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
                    </div>
                  )}

                  {/* Bubble */}
                  <div className={`p-4 rounded-2xl text-sm leading-relaxed shadow-sm ${
                    msg.role === "agent" 
                    ? "bg-white/5 border border-white/10 rounded-bl-sm text-gray-200" 
                    : "bg-blue-600 border border-blue-500 rounded-br-sm text-white shadow-blue-900/20"
                  }`}>
                    {msg.role === "agent" ? (
                      <div className="space-y-2 [&_p]:mb-2 [&_p:last-child]:mb-0 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:mb-2 [&_li]:mb-1 [&_strong]:text-white [&_strong]:font-bold [&_a]:text-blue-400 [&_a]:underline [&_a]:hover:text-blue-300 [&_h3]:text-base [&_h3]:font-bold [&_h3]:text-emerald-400 [&_h3]:mt-3 [&_h3]:mb-1">
                        <ReactMarkdown>
                          {idx === 0 ? t('welcome_message') : msg.content}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      msg.content
                    )}
                  </div>
                </div>
              </div>
            ))}
            
            {isLoading && (
              <div className="flex items-end gap-2 max-w-[85%]">
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-emerald-400 to-teal-600 flex-shrink-0 flex items-center justify-center mb-1">
                  <span className="text-[10px] font-black text-white">N</span>
                </div>
                <div className="p-4 rounded-2xl bg-white/5 border border-white/10 rounded-bl-sm flex gap-1.5 items-center">
                  <div className="w-1.5 h-1.5 rounded-full bg-gray-500 animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-1.5 h-1.5 rounded-full bg-gray-500 animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-1.5 h-1.5 rounded-full bg-gray-500 animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
              </div>
            )}
          </div>

          {/* Input Alanı */}
          <div className="p-5 border-t border-white/5 bg-black/40">
            <div className="relative flex items-center">
              <input 
                type="text" 
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                placeholder={t('chat_placeholder')} 
                className="w-full pl-5 pr-14 py-4 rounded-xl bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500/50 focus:bg-white/10 transition-all text-sm shadow-inner"
              />
              <button 
                onClick={handleSend}
                disabled={isLoading || !input.trim()}
                className="absolute right-2 p-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-all disabled:opacity-30 disabled:hover:bg-blue-600"
              >
                <svg className="w-5 h-5 translate-x-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
              </button>
            </div>
          </div>
        </div>

        {/* Sağ Panel - Dashboard */}
        <div className="flex-1 p-8 md:p-12 flex flex-col gap-8 overflow-y-auto relative z-10 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-thumb]:rounded-full">
          
          {/* Dashboard Header */}
          <div className="flex justify-between items-end pb-6 border-b border-white/10">
             <div>
                <h2 className="text-3xl font-black tracking-tight text-white">{t('panel_title')}</h2>
                <p className="text-gray-400 text-sm mt-1">Real-time Data Lakehouse & Verification Engine</p>
             </div>
             <div className="flex items-center gap-2">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                </span>
                <span className="text-xs font-bold text-emerald-400 bg-emerald-500/10 px-3 py-1.5 rounded-full border border-emerald-500/20">System Online</span>
             </div>
          </div>
          
          {/* İstatistik / Bilgi Kartları */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div className="p-6 bg-gradient-to-br from-emerald-500/10 to-transparent border border-emerald-500/20 rounded-2xl shadow-lg relative overflow-hidden group hover:border-emerald-500/40 transition-colors">
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <svg className="w-16 h-16 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              </div>
              <h3 className="text-emerald-400 font-bold text-xs uppercase tracking-wider mb-2">Verification Status</h3>
              <p className="text-white font-medium text-sm leading-relaxed pr-10">{t('verifier_active')}</p>
            </div>
            
            <div className="p-6 bg-gradient-to-br from-blue-500/10 to-transparent border border-blue-500/20 rounded-2xl shadow-lg relative overflow-hidden group hover:border-blue-500/40 transition-colors">
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <svg className="w-16 h-16 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" /></svg>
              </div>
              <h3 className="text-blue-400 font-bold text-xs uppercase tracking-wider mb-2">Data Lake Sources</h3>
              <p className="text-white font-medium text-sm leading-relaxed pr-10">{t('sources')}</p>
            </div>
          </div>

          {/* Grafik Alanı (Boş Durum) */}
          <div className="flex-1 min-h-[400px] bg-white/[0.02] border border-white/5 rounded-3xl p-8 flex flex-col items-center justify-center relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-blue-900/5 to-purple-900/5 pointer-events-none"></div>
            
            {/* Arkaplan Izgarası (Grid) */}
            <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiIGZpbGw9InJnYmEoMjU1LDI1NSwyNTUsMC4wNSkiLz48L3N2Zz4=')] opacity-50"></div>

            <div className="z-10 flex flex-col items-center text-center max-w-md">
              <div className="w-20 h-20 bg-white/5 rounded-2xl flex items-center justify-center border border-white/10 mb-6 group-hover:scale-110 group-hover:border-blue-500/30 transition-all duration-500 shadow-xl">
                <svg className="w-10 h-10 text-gray-500 group-hover:text-blue-400 transition-colors duration-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <h3 className="text-xl font-bold text-gray-200 mb-2">{t('graph_placeholder')}</h3>
              <p className="text-gray-500 text-sm leading-relaxed">{t('graph_subtext')}</p>
              
              <div className="mt-8 flex gap-2">
                <div className="h-1.5 w-12 bg-white/10 rounded-full overflow-hidden">
                   <div className="h-full bg-blue-500/50 w-1/3 animate-pulse"></div>
                </div>
                <div className="h-1.5 w-8 bg-white/10 rounded-full"></div>
                <div className="h-1.5 w-16 bg-white/10 rounded-full overflow-hidden">
                   <div className="h-full bg-emerald-500/50 w-1/2 animate-pulse delay-75"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Login Screen
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-[#050505] text-gray-200 p-4 relative font-sans overflow-hidden selection:bg-blue-500/30">
      
      {/* Arka plan efektleri */}
      <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiIGZpbGw9InJnYmEoMjU1LDI1NSwyNTUsMC4wMykiLz48L3N2Zz4=')] opacity-50"></div>
      <div className="absolute top-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full bg-blue-900/20 blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full bg-emerald-900/10 blur-[120px] pointer-events-none"></div>

      {/* Dil Seçimi */}
      <div className="absolute top-6 right-6 flex gap-2 z-20">
        <Link href="/tr" className="px-3.5 py-1.5 bg-white/5 backdrop-blur-md rounded-lg border border-white/10 hover:bg-white/10 hover:border-white/20 transition-all font-semibold text-xs tracking-wider">TR</Link>
        <Link href="/en" className="px-3.5 py-1.5 bg-white/5 backdrop-blur-md rounded-lg border border-white/10 hover:bg-white/10 hover:border-white/20 transition-all font-semibold text-xs tracking-wider">EN</Link>
      </div>

      <div className="max-w-md w-full bg-white/[0.03] backdrop-blur-3xl rounded-[2rem] shadow-2xl p-10 text-center border border-white/10 relative z-10 group">
        
        {/* İç aydınlatma efekti */}
        <div className="absolute inset-0 bg-gradient-to-b from-white/5 to-transparent rounded-[2rem] pointer-events-none"></div>

        <div className="w-20 h-20 mx-auto bg-gradient-to-tr from-blue-600 to-emerald-400 rounded-2xl flex items-center justify-center shadow-2xl shadow-blue-500/20 mb-8 border border-white/20 group-hover:scale-105 transition-transform duration-500">
           <svg className="w-10 h-10 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
        </div>

        <h1 className="text-3xl font-black mb-3 bg-clip-text text-transparent bg-gradient-to-r from-white via-gray-200 to-gray-400 tracking-tight">{t('title')}</h1>
        <p className="text-emerald-400/80 mb-10 text-sm font-semibold tracking-wide uppercase">{t('subtitle')}</p>

        <p className="text-gray-400 mb-6 font-medium text-sm leading-relaxed px-4">{t('login_prompt')}</p>
        
        <button 
          onClick={() => signIn("google")} 
          className="w-full flex items-center justify-center gap-3 py-4 px-4 bg-white text-black hover:bg-gray-100 font-bold rounded-xl transition-all hover:scale-[1.02] active:scale-95 shadow-xl shadow-white/10 mb-6"
        >
          {/* Google SVG */}
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
          </svg>
          {t('login_button')}
        </button>

        <div className="relative my-8">
          <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-white/5"></div></div>
          <div className="relative flex justify-center text-xs uppercase tracking-widest"><span className="px-4 bg-[#0a0a0a] rounded-full text-gray-500 font-bold border border-white/5 py-1">veya</span></div>
        </div>

        <button 
          onClick={() => toggleDevMode(true)} 
          className="w-full py-4 px-4 bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white font-bold rounded-xl transition-all border border-white/10 hover:border-white/20 shadow-inner group/dev"
        >
          <span className="flex items-center justify-center gap-2">
            <svg className="w-5 h-5 text-gray-500 group-hover/dev:text-blue-400 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>
            Geliştirici Modu (Bypass)
          </span>
        </button>
      </div>
      
      {/* Footer / Copyright */}
      <div className="absolute bottom-6 text-center text-xs text-gray-600 font-medium">
         &copy; 2026 KKB Hackathon - Data Lakehouse & AI Agent
      </div>
    </div>
  );
}

export default function Home() {
  const t = useTranslations('Index');

  return (
    <SessionProvider>
      <DashboardContent t={t} />
    </SessionProvider>
  );
}