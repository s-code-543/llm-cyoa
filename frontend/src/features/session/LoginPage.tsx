import { useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { Alert, Button, Card, Input, Label, TextField } from "@heroui/react";
import { useSession } from "./SessionProvider";

// Only follow same-origin paths so ?next cannot redirect off-site.
export const safeNext = (value: string | null) => {
  if (!value?.startsWith("/")) return "/";
  try {
    const url = new URL(value, window.location.origin);
    return url.origin === window.location.origin
      ? `${url.pathname}${url.search}${url.hash}`
      : "/";
  } catch {
    return "/";
  }
};

export function LoginPage() {
  const { session, login } = useSession();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const next = safeNext(params.get("next"));
  if (session?.user) return <Navigate to={next} replace />;
  function submit(event: FormEvent) {
    event.preventDefault();
    login.mutate(
      { username, password },
      { onSuccess: () => void navigate(next, { replace: true }) },
    );
  }
  return (
    <main className="mx-auto max-w-md px-4 py-16">
      <Card className="p-4">
        <Card.Header className="items-center text-center">
          <span className="text-4xl text-sun">✦</span>
          <Card.Title className="font-story text-3xl">Welcome back</Card.Title>
          <Card.Description>
            Sign in to continue your adventures.
          </Card.Description>
        </Card.Header>
        <Card.Content>
          <form className="flex flex-col gap-4" onSubmit={submit}>
            <TextField isRequired value={username} onChange={setUsername}>
              <Label>Username</Label>
              <Input autoComplete="username" />
            </TextField>
            <TextField
              isRequired
              type="password"
              value={password}
              onChange={setPassword}
            >
              <Label>Password</Label>
              <Input autoComplete="current-password" />
            </TextField>
            {login.error && (
              <Alert status="danger" role="alert">
                <Alert.Content>
                  <Alert.Description>{login.error.message}</Alert.Description>
                </Alert.Content>
              </Alert>
            )}
            <Button
              type="submit"
              variant="primary"
              className="text-white bg-linear-to-r from-brand to-brand-coral"
              isDisabled={login.isPending}
            >
              {login.isPending ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </Card.Content>
      </Card>
    </main>
  );
}
