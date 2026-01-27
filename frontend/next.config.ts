import type { NextConfig } from "next";
import dotenv from 'dotenv';
import path from 'path';

// Load root .env file (from nouva root)
// process.cwd() is usually frontend/ when running npm run dev
dotenv.config({ path: path.resolve(process.cwd(), '../.env') });

const nextConfig: NextConfig = {
  env: {
    // Map backend env vars to Frontend public vars
    NEXT_PUBLIC_SUPABASE_URL: process.env.SUPABASE_URL,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.SUPABASE_ANON_KEY,
    // Add fallback for backend URL
    NEXT_PUBLIC_BACKEND_URL: process.env.BACKEND_URL || 'http://localhost:8000',
  }
};

export default nextConfig;
