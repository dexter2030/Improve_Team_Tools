CREATE TABLE "drafts" (
	"match_id" text PRIMARY KEY NOT NULL,
	"patch" text,
	"league" text NOT NULL,
	"game_date" timestamp with time zone,
	"blue_team" text,
	"red_team" text,
	"blue_bans" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"red_bans" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"b1_pick" text,
	"r1_pick" text,
	"r2_pick" text,
	"b2_pick" text,
	"b3_pick" text,
	"r3_pick" text,
	"b4_pick" text,
	"b5_pick" text,
	"r4_pick" text,
	"r5_pick" text,
	"winner" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "league_sync" (
	"league" text PRIMARY KEY NOT NULL,
	"last_fetched" timestamp with time zone,
	"last_game_date" timestamp with time zone,
	"remote_total" integer,
	"remote_checked" timestamp with time zone
);
--> statement-breakpoint
CREATE INDEX "drafts_league_idx" ON "drafts" USING btree ("league");--> statement-breakpoint
CREATE INDEX "drafts_patch_idx" ON "drafts" USING btree ("patch");--> statement-breakpoint
CREATE INDEX "drafts_b1_idx" ON "drafts" USING btree ("b1_pick");--> statement-breakpoint
CREATE INDEX "drafts_game_date_idx" ON "drafts" USING btree ("game_date");