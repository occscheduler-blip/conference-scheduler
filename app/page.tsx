import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen bg-[#f5f5f5] px-4 py-10">
      <div className="mx-auto flex w-full max-w-4xl flex-col items-center">
        <h1 className="mb-6 text-center text-3xl font-extrabold tracking-wide text-black md:text-5xl">
          OCC THESIS SYMPOSIUM
        </h1>

        <div className="flex flex-wrap justify-center gap-3">
          <Link
            href="/admin"
            className="rounded-md border border-[#9ca3af] bg-[#e5e7eb] px-5 py-2 text-sm font-semibold text-[#1f2937] transition hover:border-[#0f33a8] hover:bg-[#0f33a8] hover:text-white md:text-base"
          >
            Admin Page
          </Link>
          <Link
            href="/faculty"
            className="rounded-md border border-[#9ca3af] bg-[#e5e7eb] px-5 py-2 text-sm font-semibold text-[#1f2937] transition hover:border-[#0f33a8] hover:bg-[#0f33a8] hover:text-white md:text-base"
          >
            Faculty Page
          </Link>
          <Link
            href="/student"
            className="rounded-md border border-[#9ca3af] bg-[#e5e7eb] px-5 py-2 text-sm font-semibold text-[#1f2937] transition hover:border-[#0f33a8] hover:bg-[#0f33a8] hover:text-white md:text-base"
          >
            Student Page
          </Link>
        </div>
      </div>
    </main>
  );
}
