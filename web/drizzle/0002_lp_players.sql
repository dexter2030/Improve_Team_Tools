CREATE TABLE "lp_players_all" (
	"overview_page" text PRIMARY KEY NOT NULL,
	"id" text,
	"team" text,
	"role" text,
	"country" text,
	"residency" text,
	"nationality_primary" text,
	"is_retired" boolean DEFAULT false NOT NULL,
	"synced_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "lp_players_sync" (
	"id" integer PRIMARY KEY DEFAULT 1 NOT NULL,
	"last_fetched" timestamp with time zone,
	"total_count" integer
);
--> statement-breakpoint
CREATE INDEX "lp_players_role_idx" ON "lp_players_all" USING btree ("role");--> statement-breakpoint
CREATE INDEX "lp_players_country_idx" ON "lp_players_all" USING btree ("country");--> statement-breakpoint
CREATE INDEX "lp_players_team_idx" ON "lp_players_all" USING btree ("team");