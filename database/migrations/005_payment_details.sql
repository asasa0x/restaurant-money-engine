-- Migration 005: Restaurant Payment Account Details (Bank Transfer & Mobile Wallets)
-- Run in Supabase SQL Editor to enable saving Bank / Easypaisa / JazzCash details per restaurant.

ALTER TABLE public.restaurants
    ADD COLUMN IF NOT EXISTS payment_details JSONB NOT NULL DEFAULT '{}'::jsonb;
