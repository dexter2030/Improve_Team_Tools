import { notFound } from "next/navigation";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { getProfile } from "@/lib/profiles/repository";
import { EditPlayerForm } from "./edit-player-form";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function EditProfilePage({ params }: Props) {
  const { id } = await params;
  const profile = await getProfile(id);
  if (!profile) notFound();

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <Link
          href={`/scouting/${id}`}
          className={`${buttonVariants({ variant: "ghost", size: "sm" })} mb-2 -ml-2`}
        >
          <ArrowLeft className="h-4 w-4 mr-1" /> Z powrotem do profilu
        </Link>
        <h2 className="text-2xl font-semibold tracking-tight">
          Edytuj {profile.displayName}
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          Zmiany w linkach Riot ID / Leaguepedia uruchomią ponowną weryfikację.
          Statystyki SoloQ niezmienionych kont zostaną zachowane (cache).
        </p>
      </div>
      <EditPlayerForm
        id={id}
        initial={{
          displayName: profile.displayName,
          role: profile.role,
          age: profile.age,
          nationality: profile.nationality,
          lolprosUrl: profile.lolprosUrl,
          opggUrls: profile.soloq.map((s) => s.opggUrl).filter((u): u is string => !!u),
          leaguepediaUrl: profile.proplay?.leaguepediaUrl ?? "",
        }}
      />
    </div>
  );
}
