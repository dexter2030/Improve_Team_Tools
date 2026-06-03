CREATE TABLE "lp_player_stats" (
	"overview_page" text NOT NULL,
	"year" integer NOT NULL,
	"league" text NOT NULL,
	"role" text,
	"games" integer DEFAULT 0 NOT NULL,
	"wins" integer DEFAULT 0 NOT NULL,
	"winrate" double precision,
	"kda" double precision,
	"cs_per_min" double precision,
	"dpm" double precision,
	"kp" double precision,
	"gold_share" double precision,
	"synced_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "lp_player_stats_pk" UNIQUE("overview_page","year","league")
);
--> statement-breakpoint
CREATE TABLE "lp_player_stats_sync" (
	"league" text PRIMARY KEY NOT NULL,
	"last_fetched" timestamp with time zone,
	"last_game_date" timestamp with time zone,
	"count" integer
);
--> statement-breakpoint
ALTER TABLE "lp_players_all" ADD COLUMN "birthdate" timestamp with time zone;--> statement-breakpoint
CREATE INDEX "lp_player_stats_league_idx" ON "lp_player_stats" USING btree ("league");--> statement-breakpoint
CREATE INDEX "lp_player_stats_overview_idx" ON "lp_player_stats" USING btree ("overview_page");