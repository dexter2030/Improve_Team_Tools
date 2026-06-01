CREATE EXTENSION IF NOT EXISTS pg_trgm;--> statement-breakpoint
CREATE INDEX "lp_players_search_trgm" ON "lp_players_all" USING gin ("id" gin_trgm_ops,"team" gin_trgm_ops,"overview_page" gin_trgm_ops);--> statement-breakpoint
CREATE INDEX "lp_tp_search_trgm" ON "lp_tournament_players" USING gin ("id" gin_trgm_ops,"team" gin_trgm_ops,"overview_page" gin_trgm_ops);