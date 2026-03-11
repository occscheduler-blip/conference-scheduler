"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import AdminPage from "./admin";
import DepartmentHeadPage from "./department-head";
import HomePage from "./home";
import ProfessorPage from "./professor";
import StudentPage from "./student";

function PagesRouterContent() {
  const searchParams = useSearchParams();
  const view = (searchParams.get("view") ?? "home").toLowerCase();

  if (view === "admin") return <AdminPage />;
  if (view === "department-head") return <DepartmentHeadPage />;
  if (view === "professor") return <ProfessorPage />;
  if (view === "student") return <StudentPage />;
  return <HomePage />;
}

export default function PagesRouter() {
  return (
    <Suspense fallback={<HomePage />}>
      <PagesRouterContent />
    </Suspense>
  );
}
