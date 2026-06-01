ALTER TABLE "drafts" ADD COLUMN "first_pick_side" text;--> statement-breakpoint
CREATE INDEX "drafts_first_pick_side_idx" ON "drafts" USING btree ("first_pick_side");