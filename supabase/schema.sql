-- Schéma initial Supabase pour wil-app-backend.
-- À coller tel quel dans l'éditeur SQL du dashboard Supabase (SQL Editor
-- > New query > Run), une seule fois à la création du projet.
--
-- Remplace les stockages en mémoire actuels du backend :
--   _sessions                 -> sessions
--   (rien avant)               -> account_snapshots
--   _trending_hashtags_cache
--   _trending_ideas_cache      -> trending_cache
--   (rien avant)               -> niche_benchmarks

-- Sessions utilisateur (remplace le dict _sessions en mémoire). Le vrai
-- access_token TikTok reste ici, jamais transmis au client (app/web) qui
-- ne reçoit que le session_id.
create table if not exists sessions (
    session_id text primary key,
    access_token text not null,
    open_id text not null,
    created_at timestamptz not null default now(),
    expires_at timestamptz
);
create index if not exists idx_sessions_open_id on sessions (open_id);

-- Historique des analyses de compte, une ligne par analyse. Nécessaire
-- pour comparer un compte à lui-même dans le temps (diagnostic de
-- plateau, rapport de progression mensuel).
create table if not exists account_snapshots (
    id bigint generated always as identity primary key,
    open_id text not null,
    username text,
    niche_category text,
    lang text,
    total_videos_analyzed int,
    average_engagement_rate numeric,
    viral_percentage numeric,
    viral_count int,
    non_viral_count int,
    created_at timestamptz not null default now()
);
create index if not exists idx_account_snapshots_open_id on account_snapshots (open_id);
create index if not exists idx_account_snapshots_niche_lang on account_snapshots (niche_category, lang);

-- Cache des tendances (hashtags + idées), remplace les dicts en mémoire
-- _trending_hashtags_cache / _trending_ideas_cache. Le TTL de 24h reste
-- géré côté code applicatif via "cached_at", pas par SQL.
create table if not exists trending_cache (
    cache_key text not null,
    cache_type text not null check (cache_type in ('hashtags', 'ideas')),
    data jsonb not null,
    cached_at timestamptz not null default now(),
    primary key (cache_key, cache_type)
);

-- Benchmarks agrégés par catégorie de niche + langue, recalculés
-- périodiquement depuis account_snapshots (job à créer séparément).
-- Permet de comparer un compte à la moyenne des comptes similaires
-- plutôt que d'afficher un chiffre isolé. sample_size DOIT être vérifié
-- côté appli avant tout affichage (seuil minimum, ex. 20) pour ne jamais
-- montrer une moyenne peu fiable calculée sur trop peu de comptes.
create table if not exists niche_benchmarks (
    niche_category text not null,
    lang text not null,
    sample_size int not null,
    avg_engagement_rate numeric,
    avg_viral_percentage numeric,
    updated_at timestamptz not null default now(),
    primary key (niche_category, lang)
);

-- Note sécurité : ce backend accède à ces tables uniquement via la clé
-- service_role (jamais exposée au client Flutter/web), donc Row Level
-- Security n'est pas activé par défaut ici. Si un jour le client accède
-- directement à Supabase (sans passer par notre API), activer RLS sur
-- chaque table avant.
