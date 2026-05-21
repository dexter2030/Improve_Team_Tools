CREATE TYPE "public"."resolution_state" AS ENUM('resolved', 'partial', 'failed', 'unresolved');--> statement-breakpoint
CREATE TYPE "public"."role" AS ENUM('Top', 'Jungle', 'Mid', 'Bot', 'Support');--> statement-breakpoint
CREATE TABLE "api_cache" (
	"key" text PRIMARY KEY NOT NULL,
	"value" jsonb NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "proplay_identities" (
	"profile_id" uuid PRIMARY KEY NOT NULL,
	"leaguepedia_link" text NOT NULL,
	"leaguepedia_url" text,
	"current_team" text,
	"verified" boolean DEFAULT false NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "scouting_profiles" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"display_name" text NOT NULL,
	"role" "role" NOT NULL,
	"age" integer,
	"nationality" text,
	"lolpros_url" text,
	"notes" text DEFAULT '' NOT NULL,
	"resolution_state" "resolution_state" DEFAULT 'unresolved' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "soloq_accounts" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"profile_id" uuid NOT NULL,
	"riot_id" text NOT NULL,
	"platform" text NOT NULL,
	"opgg_url" text,
	"puuid" text,
	"summoner_level" integer,
	"is_resolved" boolean DEFAULT false NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "soloq_profile_riot_unique" UNIQUE("profile_id","riot_id","platform")
);
--> statement-breakpoint
ALTER TABLE "proplay_identities" ADD CONSTRAINT "proplay_identities_profile_id_scouting_profiles_id_fk" FOREIGN KEY ("profile_id") REFERENCES "public"."scouting_profiles"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "soloq_accounts" ADD CONSTRAINT "soloq_accounts_profile_id_scouting_profiles_id_fk" FOREIGN KEY ("profile_id") REFERENCES "public"."scouting_profiles"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "api_cache_expires_idx" ON "api_cache" USING btree ("expires_at");--> statement-breakpoint
CREATE INDEX "soloq_profile_idx" ON "soloq_accounts" USING btree ("profile_id");