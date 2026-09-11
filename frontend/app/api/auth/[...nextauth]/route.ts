import NextAuth from "next-auth";
import GoogleProvider from "next-auth/providers/google";

// Google Giriş Ayarları
const handler = NextAuth({
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID as string,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET as string,
    }),
  ],
  // Patron "register mantığını boşver sade google" dediği için sadece Google açık
  session: {
    strategy: "jwt",
  },
  secret: process.env.NEXTAUTH_SECRET,
});

export { handler as GET, handler as POST };