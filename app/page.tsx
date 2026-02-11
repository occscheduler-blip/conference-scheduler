import { BackendStatus } from "./components/backend-status";

export default function Home() {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col justify-center gap-8 px-6 py-20">
      <h1 className="text-4xl font-bold">Conference Scheduler</h1>
      <p className="text-lg text-zinc-700">
        Frontend is connected to a FastAPI backend and ready to query Supabase.
      </p>
      <div className="rounded-xl border border-zinc-200 p-5">
        <BackendStatus />
      </div>
      <p className="text-sm text-zinc-600">
        Set <code>NEXT_PUBLIC_BACKEND_URL</code> in your frontend environment if your backend is not
        running on <code>http://localhost:8000</code>.
      </p>
    </div>
  );
}
