ALTER TABLE "lp_player_stats" DROP CONSTRAINT "lp_player_stats_pk";--> statement-breakpoint
ALTER TABLE "lp_player_stats" ADD COLUMN "split" text DEFAULT 'Sezon' NOT NULL;--> statement-breakpoint
ALTER TABLE "lp_player_stats" ADD COLUMN "split_order" double precision DEFAULT 0 NOT NULL;--> statement-breakpoint
ALTER TABLE "lp_player_stats" ADD CONSTRAINT "lp_player_stats_pk" UNIQUE("overview_page","year","league","split");