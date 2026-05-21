CREATE TABLE "lp_tournament_players" (
	"overview_page" text NOT NULL,
	"league" text NOT NULL,
	"id" text,
	"team" text,
	"role" text,
	"country" text,
	"nationality_primary" text,
	"last_tournament" text,
	"last_tournament_start" timestamp with time zone,
	"synced_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "lp_tournament_players_pk" UNIQUE("overview_page","league")
);
--> statement-breakpoint
CREATE TABLE "lp_tournament_players_sync" (
	"league" text PRIMARY KEY NOT NULL,
	"last_fetched" timestamp with time zone,
	"count" integer
);
--> statement-breakpoint
CREATE INDEX "lp_tp_league_idx" ON "lp_tournament_players" USING btree ("league");--> statement-breakpoint
CREATE INDEX "lp_tp_role_idx" ON "lp_tournament_players" USING btree ("role");--> statement-breakpoint
CREATE INDEX "lp_tp_team_idx" ON "lp_tournament_players" USING btree ("team");