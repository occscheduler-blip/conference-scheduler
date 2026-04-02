"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import type { DepartmentOption, ProfessorRow, SavedClass } from "./types";
import { toMessage } from "../lib/utils";
import { apiFetch, apiPost, apiPut, apiDelete } from "../lib/api";

function DepartmentHeadPageContent({ token, onSignOut, entityId }: { token: string; onSignOut: () => void; entityId: string }) {
  const searchParams = useSearchParams();
  const symposiumIdFromLink = searchParams.get("symposium_id") ?? "";
  const departmentIdFromLink = searchParams.get("department_id") ?? "";
  const backendUrl = "/api/backend";
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const [symposiumOptions, setSymposiumOptions] = useState<DepartmentOption[]>([]);
  const [selectedSymposiumId, setSelectedSymposiumId] = useState<string>("");
  const [departments, setDepartments] = useState<DepartmentOption[]>([]);
  const [selectedDepartmentId, setSelectedDepartmentId] = useState<string>("");
  const [className, setClassName] = useState("");
  const [professors, setProfessors] = useState<ProfessorRow[]>([{ name: "", email: "" }]);
  const [savedClasses, setSavedClasses] = useState<SavedClass[]>([]);
  const [deployMessage, setDeployMessage] = useState<string>("");

  const [editingLocalId, setEditingLocalId] = useState<string>("");
  const [editingClassName, setEditingClassName] = useState<string>("");
  const [editingDepartmentId, setEditingDepartmentId] = useState<string>("");
  const [editingProfessors, setEditingProfessors] = useState<ProfessorRow[]>([]);

  const [departmentHeadById, setDepartmentHeadById] = useState<Map<string, { name: string; email: string }>>(new Map());
  const [isSelfProfessor, setIsSelfProfessor] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingLocalId, setDeletingLocalId] = useState<string>("");
  const [updatingLocalId, setUpdatingLocalId] = useState<string>("");
  const [message, setMessage] = useState<string>("");

  const selectedSymposiumName = useMemo(
    () => symposiumOptions.find((symposium) => symposium.id === selectedSymposiumId)?.name ?? selectedSymposiumId,
    [selectedSymposiumId, symposiumOptions]
  );


  useEffect(() => {
    let ignore = false;

    const loadSymposia = async () => {
      setLoading(true);
      setMessage("");
      try {
        const [symposiumRows, departmentRows] = await Promise.all([
          apiFetch<{ id?: string; name?: string; symposium_name?: string }>("/api/events/symposiums", { headers: authHeaders }),
          apiFetch<{ id?: string; department_name?: string; symposium_id?: string }>("/api/events/departments", { headers: authHeaders }),
        ]);
        const nextSymposiumOptions = symposiumRows
          .filter((row) => row.id)
          .map((row) => ({
            id: row.id as string,
            name: row.name ?? row.symposium_name ?? (row.id as string),
          }));

        let initialSymposiumId = symposiumIdFromLink;
        if (!initialSymposiumId && departmentIdFromLink) {
          const linkedDepartment = departmentRows.find((row) => row.id === departmentIdFromLink);
          initialSymposiumId = linkedDepartment?.symposium_id ?? "";
        }
        if (!initialSymposiumId && nextSymposiumOptions.length > 0) {
          initialSymposiumId = nextSymposiumOptions[0].id;
        }

        if (ignore) return;
        setSymposiumOptions(nextSymposiumOptions);
        setSelectedSymposiumId((current) => {
          if (current && nextSymposiumOptions.some((symposium) => symposium.id === current)) return current;
          return initialSymposiumId;
        });
      } catch (error) {
        if (ignore) return;
        const text = error instanceof Error ? error.message : "Unknown error";
        setMessage(`Failed to load page data: ${text}`);
      } finally {
        if (!ignore) setLoading(false);
      }
    };

    void loadSymposia();
    return () => {
      ignore = true;
    };
  }, [authHeaders, backendUrl, departmentIdFromLink, symposiumIdFromLink]);

  useEffect(() => {
    if (!selectedSymposiumId) {
      setDepartments([]);
      setSelectedDepartmentId("");
      setSavedClasses([]);
      return;
    }
    let ignore = false;

    // AI template: loads all classes and professors for each department via cascading parallel fetches.
    const loadSymposiumData = async () => {
      setLoading(true);
      setMessage("");
      try {
        const departmentRows = await apiFetch<{ id?: string; department_name?: string; symposium_id?: string; department_head_name?: string; email?: string }>(
          `/api/events/departments?symposium_id=${encodeURIComponent(selectedSymposiumId)}`,
          { headers: authHeaders }
        );
        const nextDepartments = departmentRows
          .filter((row) => row.id)
          .map((row) => ({ id: row.id as string, name: row.department_name ?? (row.id as string) }));
        const nextDepartmentHeadById = new Map(
          departmentRows
            .filter((row) => row.id && row.department_head_name)
            .map((row) => [row.id as string, { name: row.department_head_name as string, email: row.email ?? "" }])
        );

        const classesByDepartment = await Promise.all(
          nextDepartments.map(async (department) => {
            const classRows = await apiFetch<{ id?: string; name?: string }>(
              `/api/events/classes?department_id=${encodeURIComponent(department.id)}`,
              { headers: authHeaders }
            );
            const classes = classRows
              .filter((row) => row.id)
              .map((row) => ({
                id: row.id as string,
                name: row.name ?? (row.id as string),
              }));

            return { department, classes };
          })
        );

        const savedClassResults = await Promise.all(
          classesByDepartment.flatMap(({ department, classes }) =>
            classes.map(async (classRow) => {
              try {
                const professorRows = await apiFetch<{ id?: string; name?: string; email?: string }>(
                  `/api/events/professors?class_id=${encodeURIComponent(classRow.id)}`,
                  { headers: authHeaders }
                );
                const normalizedProfessors = professorRows.map((professor) => ({
                  id: professor.id,
                  name: professor.name ?? "",
                  email: professor.email ?? "",
                }));
                const professorIds = professorRows
                  .map((professor) => professor.id)
                  .filter((id): id is string => typeof id === "string" && id.length > 0);

                return {
                  localId: classRow.id,
                  classId: classRow.id,
                  professorIds,
                  departmentId: department.id,
                  departmentName: department.name,
                  className: classRow.name,
                  professors: normalizedProfessors,
                } as SavedClass;
              } catch {
                return {
                  localId: classRow.id,
                  classId: classRow.id,
                  professorIds: [],
                  departmentId: department.id,
                  departmentName: department.name,
                  className: classRow.name,
                  professors: [],
                } as SavedClass;
              }
            })
          )
        );

        if (ignore) return;
        setDepartments(nextDepartments);
        setDepartmentHeadById(nextDepartmentHeadById);
        setSavedClasses(savedClassResults);
        setSelectedDepartmentId((current) => {
          if (current && nextDepartments.some((department) => department.id === current)) return current;
          if (entityId && nextDepartments.some((department) => department.id === entityId)) {
            return entityId;
          }
          if (departmentIdFromLink && nextDepartments.some((department) => department.id === departmentIdFromLink)) {
            return departmentIdFromLink;
          }
          if (nextDepartments.length === 1) return nextDepartments[0].id;
          return "";
        });
      } catch (error) {
        if (ignore) return;
        const text = error instanceof Error ? error.message : "Unknown error";
        setMessage(`Failed to load page data: ${text}`);
      } finally {
        if (!ignore) setLoading(false);
      }
    };

    void loadSymposiumData();
    return () => {
      ignore = true;
    };
  }, [authHeaders, backendUrl, departmentIdFromLink, selectedSymposiumId]);


  const canSubmit = useMemo(() => {
    if (!selectedDepartmentId || !className.trim()) return false;
    if (isSelfProfessor) return Boolean(departmentHeadById.get(selectedDepartmentId));
    return professors.some((prof) => prof.name.trim() && prof.email.trim());
  }, [className, departmentHeadById, isSelfProfessor, professors, selectedDepartmentId]);

  const handleSelfProfessorChange = (checked: boolean) => {
    setIsSelfProfessor(checked);
  };


  const setProfessorField = (index: number, field: keyof ProfessorRow, value: string) => {
    setProfessors((current) => current.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  };

  const addProfessorRow = () => {
    setProfessors((current) => [...current, { name: "", email: "" }]);
  };

  const removeProfessorRow = (index: number) => {
    setProfessors((current) => (current.length === 1 ? current : current.filter((_row, i) => i !== index)));
  };

  // AI template: deletes a class and all linked professors from the backend, with a confirm dialog.
  const removeSavedClass = async (savedClass: SavedClass) => {
    const confirmed = window.confirm(`Delete class "${savedClass.className}"?`);
    if (!confirmed) return;
    setMessage("");
    setDeletingLocalId(savedClass.localId);
    try {
      if (savedClass.professorIds.length > 0) {
        await Promise.all(
          savedClass.professorIds.map((professorId) =>
            apiDelete(`/api/events/delete_professor?professor_id=${encodeURIComponent(professorId)}`, authHeaders)
          )
        );
      }

      await apiDelete(`/api/events/delete_class?class_id=${encodeURIComponent(savedClass.classId)}`, authHeaders);

      setSavedClasses((current) => current.filter((item) => item.localId !== savedClass.localId));
      setMessage(`Deleted class "${savedClass.className}".`);
    } catch (error) {
      const text = error instanceof Error ? error.message : "Unknown error";
      setMessage(`Delete failed: ${text}`);
    } finally {
      setDeletingLocalId("");
    }
  };

  const startEditSavedClass = (savedClass: SavedClass) => {
    setEditingLocalId(savedClass.localId);
    setEditingClassName(savedClass.className);
    setEditingDepartmentId(savedClass.departmentId);
    setEditingProfessors(savedClass.professors.map((professor) => ({ ...professor })));
    setMessage("");
  };

  const cancelEditSavedClass = () => {
    setEditingLocalId("");
    setEditingClassName("");
    setEditingDepartmentId("");
    setEditingProfessors([]);
  };

  const setEditingProfessorField = (index: number, field: "name" | "email", value: string) => {
    setEditingProfessors((current) => current.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  };

  // AI template: validates and updates a class and all its professors on the backend.
  const saveEditedClass = async (savedClass: SavedClass) => {
    const nextName = editingClassName.trim();
    if (!nextName) {
      setMessage("Enter a class name.");
      return;
    }
    if (!editingDepartmentId) {
      setMessage("Select a department.");
      return;
    }

    const cleanedProfessors = editingProfessors.map((professor) => ({
      id: professor.id ?? "",
      name: professor.name.trim(),
      email: professor.email.trim().toLowerCase(),
    }));
    if (cleanedProfessors.some((professor) => !professor.name || !professor.email)) {
      setMessage("Every professor must include name and email.");
      return;
    }
    if (cleanedProfessors.some((professor) => !professor.id)) {
      setMessage("Unable to update professor data: missing professor id.");
      return;
    }

    setMessage("");
    setUpdatingLocalId(savedClass.localId);
    try {
      await apiPut("/api/events/update_class", {
        class_id: savedClass.classId,
        name: nextName,
        department_id: editingDepartmentId,
      }, authHeaders);

      await Promise.all(
        cleanedProfessors.map(async (professor) => {
          await apiPut("/api/events/update_professor", {
            professor_id: professor.id,
            name: professor.name,
            email: professor.email,
          }, authHeaders);
        })
      );

      const nextDepartmentName =
        departments.find((department) => department.id === editingDepartmentId)?.name ?? editingDepartmentId;
      setSavedClasses((current) =>
        current.map((item) =>
          item.localId === savedClass.localId
            ? {
                ...item,
                className: nextName,
                departmentId: editingDepartmentId,
                departmentName: nextDepartmentName,
                professors: cleanedProfessors,
              }
            : item
        )
      );
      cancelEditSavedClass();
      setMessage(`Updated class "${nextName}".`);
    } catch (error) {
      const text = error instanceof Error ? error.message : "Unknown error";
      setMessage(`Update failed: ${text}`);
    } finally {
      setUpdatingLocalId("");
    }
  };

  const handleDeployClasses = () => {
    setDeployMessage(
      "Deploy is not connected yet. It will send each professor an email link with their professor_id in the URL."
    );
  };

  const submitProfessors = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage("");

    const headInfo = isSelfProfessor ? departmentHeadById.get(selectedDepartmentId) : undefined;
    const headId = departmentIdFromLink || selectedDepartmentId;
    const selfProfessorRow = headInfo ? { id: headId, name: headInfo.name, email: headInfo.email.trim().toLowerCase() } : null;

    const otherProfessors = professors
      .map((professor) => ({
        name: professor.name.trim(),
        email: professor.email.trim().toLowerCase(),
      }))
      .filter((professor) => professor.name && professor.email);

    const cleanProfessors = selfProfessorRow ? [selfProfessorRow, ...otherProfessors] : otherProfessors;

    if (!selectedDepartmentId) {
      setMessage("Select a department.");
      return;
    }
    if (!className.trim()) {
      setMessage("Enter a class name.");
      return;
    }
    if (cleanProfessors.length === 0) {
      setMessage("Add at least one professor with name and email.");
      return;
    }

    const departmentName =
      departments.find((department) => department.id === selectedDepartmentId)?.name ?? selectedDepartmentId;

    setSaving(true);
    try {
      const { raw: payload } = await apiPost("/api/events/add_class", {
        name: className.trim(),
        department_id: selectedDepartmentId,
        professors: cleanProfessors,
      }, authHeaders);

      const classId = payload.class_id as string | undefined;
      const professorIds = (payload.professor_ids as string[]) ?? [];
      if (!classId || !Array.isArray(professorIds)) {
        setMessage("Save failed: backend did not return class/professor IDs.");
        return;
      }

      const newClass: SavedClass = {
        localId: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        classId,
        professorIds,
        departmentId: selectedDepartmentId,
        departmentName,
        className: className.trim(),
        professors: cleanProfessors.map((professor, index) => ({
          id: professorIds[index],
          name: professor.name,
          email: professor.email,
        })),
      };
      setSavedClasses((current) => [...current, newClass]);
      setClassName("");
      setProfessors([{ name: "", email: "" }]);
      setIsSelfProfessor(false);
      setMessage(`Saved class "${newClass.className}" for ${departmentName}.`);
    } catch (error) {
      const text = error instanceof Error ? error.message : "Unknown error";
      if (text.toLowerCase().includes("load failed") || text.toLowerCase().includes("failed to fetch")) {
        setMessage(`Save failed: backend is unreachable at ${backendUrl}.`);
      } else {
        setMessage(`Save failed: ${text}`);
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#f7f9ff_0%,#f4f4f4_55%,#f1f1f1_100%)] px-4 py-8">
      <div className="mx-auto w-full max-w-6xl">
        <div className="mb-3 flex justify-end">
          <button
            type="button"
            onClick={onSignOut}
            className="rounded-md border border-[#9ca3af] bg-[#e5e7eb] px-4 py-1.5 text-sm font-semibold text-[#1f2937] transition hover:border-red-500 hover:bg-red-500 hover:text-white"
          >
            Sign Out
          </button>
        </div>
        <header className="mb-5 rounded-2xl border border-[#d8e2ff] bg-white/90 px-5 py-5 shadow-[0_10px_30px_rgba(20,44,120,0.08)] backdrop-blur">
          <h1 className="text-center text-2xl font-extrabold tracking-wide text-black md:text-4xl">
            OCC THESIS SYMPOSIUM - DEPARTMENT HEAD
          </h1>
        </header>

        <section className="rounded-2xl border border-[#d7bf92] bg-white p-4 shadow-[0_16px_30px_rgba(80,60,20,0.08)] md:p-6">
          <h2 className="text-xl font-bold text-[#111] md:text-2xl">Add Classes</h2>
          <label className="mt-4 flex flex-col gap-1">
            <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">Symposium</span>
            <select
              value={selectedSymposiumId}
              onChange={(event) => setSelectedSymposiumId(event.target.value)}
              disabled={loading || symposiumOptions.length === 0}
              className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2.5 text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">Select symposium</option>
              {symposiumOptions.map((symposium) => (
                <option key={symposium.id} value={symposium.id}>
                  {symposium.name}
                </option>
              ))}
            </select>
          </label>
          <p className="mt-2 text-sm font-semibold text-[#2d3d7a]">
            Symposium: {selectedSymposiumName || "Select a symposium"}
          </p>

          <form onSubmit={submitProfessors} className="mt-4 space-y-4">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">Department</span>
              <select
                value={selectedDepartmentId}
                onChange={(event) => { setSelectedDepartmentId(event.target.value); setIsSelfProfessor(false); setProfessors([{ name: "", email: "" }]); }}
                disabled={loading || departments.length === 0}
                className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2.5 text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <option value="">Select department</option>
                {departments.map((department) => (
                  <option key={department.id} value={department.id}>
                    {department.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">Class Name</span>
              <input
                value={className}
                onChange={(event) => setClassName(event.target.value)}
                placeholder="e.g. BIO-500 Thesis Seminar"
                className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2.5 text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
              />
            </label>

            <div className="space-y-3">
              {professors.map((professor, index) => (
                <div key={index} className="rounded-lg border border-[#d7e0ff] bg-[#fdfdff] p-3">
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_1fr_auto]">
                    <input
                      value={professor.name}
                      onChange={(event) => setProfessorField(index, "name", event.target.value)}
                      placeholder="Professor name"
                      className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2.5 text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                    />
                    <input
                      type="email"
                      value={professor.email}
                      onChange={(event) => setProfessorField(index, "email", event.target.value)}
                      placeholder="name@hamilton.edu"
                      className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2.5 text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                    />
                    <button
                      type="button"
                      onClick={() => removeProfessorRow(index)}
                      className="rounded-lg border border-[#b7b7b7] bg-white px-3 py-2 text-sm font-semibold text-[#222] transition hover:bg-[#f7f7f7]"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-[#2d3d7a]">
              <input
                type="checkbox"
                checked={isSelfProfessor}
                onChange={(event) => handleSelfProfessorChange(event.target.checked)}
                disabled={!selectedDepartmentId}
                className="h-4 w-4 rounded border-[#c7c7c7] accent-[#0f33a8]"
              />
              I am a professor of this class
            </label>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={addProfessorRow}
                className="rounded-lg border border-[#0f33a8] bg-white px-4 py-2 text-sm font-semibold text-[#0f33a8] transition hover:bg-[#eef3ff]"
              >
                Add Another Professor
              </button>
              <button
                type="submit"
                disabled={!canSubmit || saving}
                className="rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(15,51,168,0.25)] transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saving ? "Saving..." : "Save Class"}
              </button>
            </div>

            {message ? <p className="text-sm font-semibold text-[#222]">{message}</p> : null}
          </form>

          {savedClasses.length > 0 ? (
            <div className="mt-6 rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4">
              <h3 className="text-sm font-bold uppercase tracking-wide text-[#2d3d7a] md:text-base">
                Saved Classes
              </h3>
              <div className="mt-3 space-y-3">
                {savedClasses.map((savedClass) => (
                  <div key={savedClass.localId} className="rounded-lg border border-[#d7e0ff] bg-white p-3">
                    {editingLocalId === savedClass.localId ? (
                      <div className="space-y-2">
                        <label className="flex flex-col gap-1">
                          <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">Class Name</span>
                          <input
                            value={editingClassName}
                            onChange={(event) => setEditingClassName(event.target.value)}
                            className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2 text-sm text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                          />
                        </label>
                        <label className="flex flex-col gap-1">
                          <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a]">Department</span>
                          <select
                            value={editingDepartmentId}
                            onChange={(event) => setEditingDepartmentId(event.target.value)}
                            className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2 text-sm text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                          >
                            {departments.map((department) => (
                              <option key={department.id} value={department.id}>
                                {department.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <div className="space-y-2">
                          {editingProfessors.map((professor, index) => (
                            <div key={`${savedClass.localId}-edit-prof-${index}`} className="grid grid-cols-1 gap-2 md:grid-cols-2">
                              <input
                                value={professor.name}
                                onChange={(event) => setEditingProfessorField(index, "name", event.target.value)}
                                placeholder="Professor name"
                                className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2 text-sm text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                              />
                              <input
                                type="email"
                                value={professor.email}
                                onChange={(event) => setEditingProfessorField(index, "email", event.target.value)}
                                placeholder="name@hamilton.edu"
                                className="w-full rounded-lg border border-[#c7c7c7] bg-white px-3 py-2 text-sm text-black shadow-sm outline-none transition focus:border-[#1237af] focus:ring-2 focus:ring-[#c7d4ff]"
                              />
                            </div>
                          ))}
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => void saveEditedClass(savedClass)}
                            disabled={updatingLocalId === savedClass.localId}
                            className="rounded-lg bg-[#0f33a8] px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {updatingLocalId === savedClass.localId ? "Saving..." : "Save"}
                          </button>
                          <button
                            type="button"
                            onClick={cancelEditSavedClass}
                            className="rounded-lg border border-[#b7b7b7] bg-white px-3 py-1.5 text-xs font-semibold text-[#222] transition hover:bg-[#f7f7f7]"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-[#111]">
                          {savedClass.departmentName}: {savedClass.className}
                        </p>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => startEditSavedClass(savedClass)}
                            className="rounded-lg border border-[#b7b7b7] bg-white px-2.5 py-1 text-xs font-semibold text-[#222] transition hover:bg-[#f7f7f7]"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => void removeSavedClass(savedClass)}
                            disabled={deletingLocalId === savedClass.localId}
                            className="rounded-lg border border-[#b7b7b7] bg-white px-2.5 py-1 text-xs font-semibold text-[#222] transition hover:bg-[#f7f7f7]"
                          >
                            {deletingLocalId === savedClass.localId ? "Deleting..." : "Delete"}
                          </button>
                        </div>
                      </div>
                    )}
                    {editingLocalId !== savedClass.localId ? (
                      <ul className="mt-2 space-y-1 text-sm text-[#333]">
                        {savedClass.professors.map((professor, index) => (
                          <li key={`${savedClass.localId}-${index}`}>
                            {professor.name} ({professor.email})
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ))}
              </div>
              <div className="mt-4">
                <button
                  type="button"
                  onClick={handleDeployClasses}
                  className="rounded-lg bg-[#1b6e2b] px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_18px_rgba(27,110,43,0.25)] transition hover:bg-[#155622]"
                >
                  Deploy
                </button>
                {deployMessage ? <p className="mt-2 text-sm font-semibold text-[#222]">{deployMessage}</p> : null}
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}

export default function DepartmentHeadPage({ token, onSignOut, entityId }: { token: string; onSignOut: () => void; entityId: string }) {
  return (
    <Suspense fallback={<main className="min-h-screen bg-[#f5f5f5] px-4 py-8">Loading...</main>}>
      <DepartmentHeadPageContent token={token} onSignOut={onSignOut} entityId={entityId} />
    </Suspense>
  );
}
