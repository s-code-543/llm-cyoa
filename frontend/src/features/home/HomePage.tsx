import { confirmAction } from "../../components/notifications";
import { Link } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, ProgressBar } from "@heroui/react";
import { deleteGame, getHome } from "../../api/home";
import { adventureLogo } from "../../assets";

export function HomePage() {
  const cache = useQueryClient();
  const home = useQuery({ queryKey: ["home"], queryFn: getHome });
  const remove = useMutation({
    mutationFn: deleteGame,
    onSuccess: () => cache.invalidateQueries({ queryKey: ["home"] }),
  });
  if (home.isPending)
    return (
      <p className="p-10 text-center text-muted" role="status">
        Loading adventures…
      </p>
    );
  if (home.error)
    return (
      <p className="p-10 text-center text-danger" role="alert">
        {home.error.message}
      </p>
    );
  const { recent_games: recent, configurations } = home.data;
  const tints = [
    "bg-grape-soft",
    "bg-coral-soft",
    "bg-mint-soft",
    "bg-sun-soft",
    "bg-sky-soft",
  ];
  return (
    <main className="mx-auto max-w-7xl px-4 py-10">
      <h1 className="mx-auto text-center font-story text-4xl font-bold text-grape sm:text-5xl">
        <img
          src={adventureLogo}
          alt=""
          className="mx-auto h-auto w-full max-w-2xl object-contain"
        />
        <span className="sr-only">Choose your adventure</span>
      </h1>
      {recent.length > 0 && (
        <section aria-labelledby="continue" className="mt-10">
          <h2 id="continue" className="mb-4 text-xl font-bold">
            Continue playing
          </h2>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {recent.map((game) => (
              <li key={game.id}>
                <Card
                  className={`h-full ${game.unavailable_reason ? "opacity-50 grayscale" : ""}`}
                >
                  <Card.Content className="gap-3">
                    <Link
                      aria-disabled={Boolean(game.unavailable_reason)}
                      title={game.unavailable_reason ?? undefined}
                      onClick={(event) => {
                        if (game.unavailable_reason) event.preventDefault();
                      }}
                      to={`/chat?conversation_id=${game.id}`}
                      className="flex flex-col gap-2"
                    >
                      <strong className="font-story text-xl">
                        {game.title}
                      </strong>
                      <ProgressBar
                        aria-label={`Progress for ${game.title}`}
                        minValue={0}
                        maxValue={game.max_turns}
                        value={game.turn}
                        color="accent"
                      >
                        <ProgressBar.Track>
                          <ProgressBar.Fill />
                        </ProgressBar.Track>
                      </ProgressBar>
                      <span className="text-sm text-muted">
                        Turn {game.turn}/{game.max_turns}
                      </span>
                    </Link>
                    {game.unavailable_reason && (
                      <p className="text-sm">{game.unavailable_reason}</p>
                    )}
                    <Button
                      size="sm"
                      variant="danger-soft"
                      className="self-start"
                      isDisabled={remove.isPending}
                      onPress={async () => {
                        if (await confirmAction(`Delete “${game.title}”?`))
                          remove.mutate(game.id);
                      }}
                    >
                      Delete
                    </Button>
                  </Card.Content>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section aria-labelledby="start" className="mt-10">
        <h2 id="start" className="mb-4 text-xl font-bold">
          Start a new adventure
        </h2>
        {configurations.length === 0 ? (
          <p className="text-muted">No adventures are available yet.</p>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {configurations.map((config, i) => (
              <li key={config.id}>
                <Link
                  to={`/chat?config=${config.id}`}
                  className={`flex h-full flex-col gap-2 rounded-3xl p-6 shadow-md transition hover:-translate-y-1 hover:shadow-xl ${tints[i % tints.length]}`}
                >
                  <strong className="font-story text-2xl">{config.name}</strong>
                  {config.description && (
                    <span className="text-foreground/80">
                      {config.description}
                    </span>
                  )}
                  <small className="mt-auto pt-2 font-bold text-grape">
                    {config.total_turns} turns
                    {config.difficulty ? ` · ${config.difficulty}` : ""} →
                  </small>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
