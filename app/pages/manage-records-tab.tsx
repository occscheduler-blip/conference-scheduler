"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { apiDelete, apiFetch, apiPost, apiPut } from "../lib/api";
import { FIELD_CLASS as fieldClass } from "../lib/styles";
import type {
  ClassRecord,
  DepartmentRecord,
  PresentationRecord,
  ProfessorRecord,
  StudentRecord,
  SymposiumOption,
} from "./types";
import AvailabilityEditor from "./availability-editor";

type RecordSection = "classes" | "professors" | "students" | "presentations";
type FormMode = "add" | "edit";
type AvailabilityTarget = {
  linkedId: string;
  entityName: string;
  entityKind: "Professor" | "Student";
};

const buttonClass =
  "rounded-lg bg-[#0f33a8] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#0b2a8d] disabled:cursor-not-allowed disabled:opacity-60";
const secondaryButtonClass =
  "rounded-lg border border-[#bdbdbd] bg-white px-3 py-1.5 text-sm font-semibold text-[#333] transition hover:border-[#0f33a8] hover:text-[#0f33a8] disabled:cursor-not-allowed disabled:opacity-60";
const dangerButtonClass =
  "rounded-lg border border-[#b00020] bg-white px-3 py-1.5 text-sm font-semibold text-[#b00020] transition hover:bg-[#fff5f6] disabled:cursor-not-allowed disabled:opacity-60";

function selectedValues(options: HTMLOptionsCollection): string[] {
  return Array.from(options).filter((option) => option.selected).map((option) => option.value);
}

function presentationStudentIds(presentation: PresentationRecord): string[] {
  return (presentation.presenting_students ?? []).map((student) => student.id);
}

function presentationProfessorIds(presentation: PresentationRecord): string[] {
  return (presentation.assigned_professors ?? []).map((professor) => professor.id);
}

export default function ManageRecordsTab({ token }: { token: string }) {
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const [symposiums, setSymposiums] = useState<SymposiumOption[]>([]);
  const [departments, setDepartments] = useState<DepartmentRecord[]>([]);
  const [classes, setClasses] = useState<ClassRecord[]>([]);
  const [students, setStudents] = useState<StudentRecord[]>([]);
  const [professors, setProfessors] = useState<ProfessorRecord[]>([]);
  const [departmentProfessors, setDepartmentProfessors] = useState<ProfessorRecord[]>([]);
  const [presentations, setPresentations] = useState<PresentationRecord[]>([]);

  const [selectedSymposiumId, setSelectedSymposiumId] = useState("");
  const [selectedDepartmentId, setSelectedDepartmentId] = useState("");
  const [selectedClassId, setSelectedClassId] = useState("");
  const [activeSection, setActiveSection] = useState<RecordSection>("classes");

  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<"success" | "error" | null>(null);

  const [classMode, setClassMode] = useState<FormMode>("add");
  const [classId, setClassId] = useState("");
  const [className, setClassName] = useState("");

  const [professorMode, setProfessorMode] = useState<FormMode>("add");
  const [professorId, setProfessorId] = useState("");
  const [professorName, setProfessorName] = useState("");
  const [professorEmail, setProfessorEmail] = useState("");

  const [studentMode, setStudentMode] = useState<FormMode>("add");
  const [studentId, setStudentId] = useState("");
  const [studentName, setStudentName] = useState("");
  const [studentEmail, setStudentEmail] = useState("");

  const [presentationMode, setPresentationMode] = useState<FormMode>("add");
  const [presentationId, setPresentationId] = useState("");
  const [presentationTitle, setPresentationTitle] = useState("");
  const [presentationMinutes, setPresentationMinutes] = useState("20");
  const [presentationBuffer, setPresentationBuffer] = useState("0");
  const [presentationStudentIdsState, setPresentationStudentIdsState] = useState<string[]>([]);
  const [presentationProfessorIdsState, setPresentationProfessorIdsState] = useState<string[]>([]);
  const [emailStudentsAfterPresentationAdd, setEmailStudentsAfterPresentationAdd] = useState(true);

  const [availabilityTarget, setAvailabilityTarget] = useState<AvailabilityTarget | null>(null);

  const selectedDepartment = departments.find((department) => department.id === selectedDepartmentId);
  const selectedClass = classes.find((classRecord) => classRecord.id === selectedClassId);

  const showMessage = (text: string, kind: "success" | "error") => {
    setMessage(text);
    setMessageKind(kind);
  };

  const openAvailability = (target: AvailabilityTarget) => {
    if (!selectedSymposiumId) {
      showMessage("Select a symposium first.", "error");
      return;
    }
    setAvailabilityTarget(target);
  };

  const resetClassForm = () => {
    setClassMode("add");
    setClassId("");
    setClassName("");
  };

  const resetProfessorForm = () => {
    setProfessorMode("add");
    setProfessorId("");
    setProfessorName("");
    setProfessorEmail("");
  };

  const resetStudentForm = () => {
    setStudentMode("add");
    setStudentId("");
    setStudentName("");
    setStudentEmail("");
  };

  const resetPresentationForm = () => {
    setPresentationMode("add");
    setPresentationId("");
    setPresentationTitle("");
    setPresentationMinutes("20");
    setPresentationBuffer("0");
    setPresentationStudentIdsState([]);
    setPresentationProfessorIdsState([]);
  };

  const fetchSymposiums = useCallback(async () => {
    setIsLoading(true);
    try {
      const rows = await apiFetch<SymposiumOption>("/api/events/symposiums", { headers: authHeaders });
      setSymposiums(rows);
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "Failed to load symposiums.", "error");
    } finally {
      setIsLoading(false);
    }
  }, [authHeaders]);

  const fetchDepartments = useCallback(async (symposiumId: string) => {
    if (!symposiumId) {
      setDepartments([]);
      return;
    }
    setIsLoading(true);
    try {
      const rows = await apiFetch<DepartmentRecord>(
        `/api/events/departments?symposium_id=${encodeURIComponent(symposiumId)}`,
        { headers: authHeaders }
      );
      setDepartments(rows);
      setSelectedDepartmentId((current) => (rows.some((row) => row.id === current) ? current : rows[0]?.id ?? ""));
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "Failed to load departments.", "error");
      setDepartments([]);
    } finally {
      setIsLoading(false);
    }
  }, [authHeaders]);

  const fetchClasses = useCallback(async (departmentId: string) => {
    if (!departmentId) {
      setClasses([]);
      setDepartmentProfessors([]);
      return;
    }
    setIsLoading(true);
    try {
      const rows = await apiFetch<ClassRecord>(
        `/api/events/classes?department_id=${encodeURIComponent(departmentId)}`,
        { headers: authHeaders }
      );
      setClasses(rows);
      setSelectedClassId((current) => (rows.some((row) => row.id === current) ? current : rows[0]?.id ?? ""));
      if (rows.length > 0) {
        const classIdParam = rows.map((row) => row.id).join(",");
        const professorRows = await apiFetch<ProfessorRecord>(
          `/api/events/professors?class_id=${encodeURIComponent(classIdParam)}`,
          { headers: authHeaders }
        );
        setDepartmentProfessors(professorRows);
      } else {
        setDepartmentProfessors([]);
      }
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "Failed to load classes.", "error");
      setClasses([]);
      setDepartmentProfessors([]);
    } finally {
      setIsLoading(false);
    }
  }, [authHeaders]);

  const fetchClassChildren = useCallback(async (classRecordId: string) => {
    if (!classRecordId) {
      setStudents([]);
      setProfessors([]);
      setPresentations([]);
      return;
    }
    setIsLoading(true);
    try {
      const [studentRows, professorRows, presentationRows] = await Promise.all([
        apiFetch<StudentRecord>(`/api/events/students?class_id=${encodeURIComponent(classRecordId)}`, { headers: authHeaders }),
        apiFetch<ProfessorRecord>(`/api/events/professors?class_id=${encodeURIComponent(classRecordId)}`, { headers: authHeaders }),
        apiFetch<PresentationRecord>(`/api/events/presentations?class_id=${encodeURIComponent(classRecordId)}`, { headers: authHeaders }),
      ]);
      setStudents(studentRows);
      setProfessors(professorRows);
      setPresentations(presentationRows);
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "Failed to load class records.", "error");
      setStudents([]);
      setProfessors([]);
      setPresentations([]);
    } finally {
      setIsLoading(false);
    }
  }, [authHeaders]);

  useEffect(() => {
    void fetchSymposiums();
  }, [fetchSymposiums]);

  useEffect(() => {
    setSelectedDepartmentId("");
    setSelectedClassId("");
    setClasses([]);
    setDepartmentProfessors([]);
    setStudents([]);
    setProfessors([]);
    setPresentations([]);
    resetClassForm();
    resetProfessorForm();
    resetStudentForm();
    resetPresentationForm();
    void fetchDepartments(selectedSymposiumId);
  }, [fetchDepartments, selectedSymposiumId]);

  useEffect(() => {
    setSelectedClassId("");
    setStudents([]);
    setProfessors([]);
    setPresentations([]);
    resetClassForm();
    resetProfessorForm();
    resetStudentForm();
    resetPresentationForm();
    void fetchClasses(selectedDepartmentId);
  }, [fetchClasses, selectedDepartmentId]);

  useEffect(() => {
    resetProfessorForm();
    resetStudentForm();
    resetPresentationForm();
    void fetchClassChildren(selectedClassId);
  }, [fetchClassChildren, selectedClassId]);

  const refreshCurrentScope = async () => {
    if (selectedDepartmentId) {
      await fetchClasses(selectedDepartmentId);
    }
    if (selectedClassId) {
      await fetchClassChildren(selectedClassId);
    }
  };

  const handleClassSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedDepartmentId) {
      showMessage("Select a department first.", "error");
      return;
    }
    if (!className.trim()) {
      showMessage("Enter a class name.", "error");
      return;
    }
    try {
      let nextClassId = "";
      if (classMode === "add") {
        const { raw } = await apiPost("/api/events/add_class", {
          department_id: selectedDepartmentId,
          name: className.trim(),
          professors: [],
        }, authHeaders);
        nextClassId = String(raw.class_id ?? "");
        showMessage("Class added.", "success");
      } else {
        await apiPut("/api/events/update_class", {
          class_id: classId,
          department_id: selectedDepartmentId,
          name: className.trim(),
        }, authHeaders);
        showMessage("Class updated.", "success");
      }
      resetClassForm();
      await fetchClasses(selectedDepartmentId);
      if (nextClassId) {
        setSelectedClassId(nextClassId);
      }
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "Failed to save class.", "error");
    }
  };

  const handleProfessorSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedClassId) {
      showMessage("Select a class first.", "error");
      return;
    }
    if (!professorName.trim() || !professorEmail.trim()) {
      showMessage("Enter professor name and email.", "error");
      return;
    }
    try {
      if (professorMode === "add") {
        await apiPost("/api/events/add_professor", {
          class_id: selectedClassId,
          name: professorName.trim(),
          email: professorEmail.trim().toLowerCase(),
        }, authHeaders);
        showMessage("Professor added.", "success");
      } else {
        await apiPut("/api/events/update_professor", {
          professor_id: professorId,
          class_id: selectedClassId,
          name: professorName.trim(),
          email: professorEmail.trim().toLowerCase(),
        }, authHeaders);
        showMessage("Professor updated.", "success");
      }
      resetProfessorForm();
      if (selectedDepartmentId) {
        await fetchClasses(selectedDepartmentId);
      }
      await fetchClassChildren(selectedClassId);
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "Failed to save professor.", "error");
    }
  };

  const handleStudentSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedClassId) {
      showMessage("Select a class first.", "error");
      return;
    }
    if (!studentName.trim() || !studentEmail.trim()) {
      showMessage("Enter student name and email.", "error");
      return;
    }
    try {
      if (studentMode === "add") {
        await apiPost("/api/events/add_students", {
          class_id: selectedClassId,
          students: [{ name: studentName.trim(), email: studentEmail.trim().toLowerCase() }],
        }, authHeaders);
        showMessage("Student added.", "success");
      } else {
        const existing = students.find((student) => student.id === studentId);
        await apiPut("/api/events/update_student", {
          student_id: studentId,
          class_id: selectedClassId,
          presentation_id: existing?.presentation_id ?? null,
          name: studentName.trim(),
          email: studentEmail.trim().toLowerCase(),
        }, authHeaders);
        showMessage("Student updated.", "success");
      }
      resetStudentForm();
      await fetchClassChildren(selectedClassId);
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "Failed to save student.", "error");
    }
  };

  const handlePresentationSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedClassId) {
      showMessage("Select a class first.", "error");
      return;
    }
    const minutes = Number.parseInt(presentationMinutes, 10);
    const buffer = Number.parseInt(presentationBuffer, 10);
    if (!presentationTitle.trim() || !Number.isFinite(minutes) || minutes < 1 || !Number.isFinite(buffer) || buffer < 0) {
      showMessage("Enter a title, duration, and buffer.", "error");
      return;
    }
    try {
      if (presentationMode === "add") {
        const { raw } = await apiPost("/api/events/add_presentation", {
          class_id: selectedClassId,
          title: presentationTitle.trim(),
          minutes,
          buffer,
          presenting_students: presentationStudentIdsState,
          assigned_professors: presentationProfessorIdsState,
        }, authHeaders);
        const newPresentationId = String(raw.presentation_id ?? "");
        if (emailStudentsAfterPresentationAdd && newPresentationId && presentationStudentIdsState.length > 0) {
          const { raw: emailResult } = await apiPost("/api/events/email_students", { presentation_id: newPresentationId }, authHeaders);
          const count = Number(emailResult.emails_sent ?? 0);
          showMessage(`Presentation added and emailed ${count} student${count === 1 ? "" : "s"}.`, "success");
        } else {
          showMessage("Presentation added.", "success");
        }
      } else {
        const existing = presentations.find((presentation) => presentation.id === presentationId);
        await apiPut("/api/events/update_presentation", {
          presentation_id: presentationId,
          class_id: selectedClassId,
          title: presentationTitle.trim(),
          minutes,
          buffer,
          room: existing?.room ?? null,
          presenting_students: presentationStudentIdsState,
          assigned_professors: presentationProfessorIdsState,
        }, authHeaders);
        showMessage("Presentation updated.", "success");
      }
      resetPresentationForm();
      await fetchClassChildren(selectedClassId);
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "Failed to save presentation.", "error");
    }
  };

  const deleteRecord = async (path: string, label: string) => {
    if (!window.confirm(`Delete ${label}? This can also remove related availability, requests, or schedule data.`)) return;
    try {
      await apiDelete(path, authHeaders);
      showMessage(`${label} deleted.`, "success");
      await refreshCurrentScope();
    } catch (error) {
      showMessage(error instanceof Error ? error.message : `Failed to delete ${label}.`, "error");
    }
  };

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-4 rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4 md:grid-cols-3 md:p-5">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Symposium</span>
          <select className={fieldClass} value={selectedSymposiumId} onChange={(event) => setSelectedSymposiumId(event.target.value)}>
            <option value="">Select symposium...</option>
            {symposiums.map((symposium) => (
              <option key={symposium.id} value={symposium.id}>{symposium.name}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Department</span>
          <select className={fieldClass} value={selectedDepartmentId} onChange={(event) => setSelectedDepartmentId(event.target.value)} disabled={!selectedSymposiumId}>
            <option value="">Select department...</option>
            {departments.map((department) => (
              <option key={department.id} value={department.id}>{department.department_name}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Class</span>
          <select className={fieldClass} value={selectedClassId} onChange={(event) => setSelectedClassId(event.target.value)} disabled={!selectedDepartmentId}>
            <option value="">Select class...</option>
            {classes.map((classRecord) => (
              <option key={classRecord.id} value={classRecord.id}>{classRecord.name}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="rounded-lg border border-[#e0e0e0] bg-[#f9f9f9] p-3 text-sm font-semibold text-[#333]">
        {isLoading
          ? "Loading records..."
          : selectedClass
            ? `Managing ${selectedClass.name}${selectedDepartment ? ` in ${selectedDepartment.department_name}` : ""}.`
            : selectedDepartment
              ? `Managing classes in ${selectedDepartment.department_name}.`
              : "Choose a symposium and department to start managing records."}
      </div>

      {message ? (
        <p className={`text-sm font-semibold ${messageKind === "error" ? "text-[#9a1f1f]" : "text-[#1f5132]"}`}>
          {message}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {(["classes", "professors", "students", "presentations"] as RecordSection[]).map((section) => (
          <button
            key={section}
            type="button"
            onClick={() => setActiveSection(section)}
            className={`rounded-lg border px-4 py-2 text-sm font-bold capitalize transition ${
              activeSection === section ? "border-[#0f33a8] bg-[#0f33a8] text-white" : "border-[#c6d2f6] bg-white text-[#111] hover:border-[#0f33a8]"
            }`}
          >
            {section}
          </button>
        ))}
      </div>

      {activeSection === "classes" ? (
        <section className="rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4 md:p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h3 className="text-lg font-bold text-[#111]">Classes</h3>
            {classMode === "edit" ? <button type="button" onClick={resetClassForm} className={secondaryButtonClass}>Cancel Edit</button> : null}
          </div>
          <form onSubmit={handleClassSubmit} className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto]">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Class Name</span>
              <input className={fieldClass} value={className} onChange={(event) => setClassName(event.target.value)} disabled={!selectedDepartmentId} />
            </label>
            <div className="flex items-end">
              <button type="submit" className={buttonClass} disabled={!selectedDepartmentId}>{classMode === "add" ? "Add Class" : "Save Class"}</button>
            </div>
          </form>
          <div className="mt-4 space-y-2">
            {classes.length === 0 ? <p className="text-sm text-[#555]">No classes found.</p> : classes.map((classRecord) => (
              <div key={classRecord.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#e5e7eb] bg-white p-3">
                <button type="button" onClick={() => setSelectedClassId(classRecord.id)} className="text-left text-sm font-semibold text-[#111] hover:text-[#0f33a8]">
                  {classRecord.name}
                </button>
                <div className="flex gap-2">
                  <button type="button" className={secondaryButtonClass} onClick={() => {
                    setClassMode("edit");
                    setClassId(classRecord.id);
                    setClassName(classRecord.name);
                  }}>Edit</button>
                  <button type="button" className={dangerButtonClass} onClick={() => void deleteRecord(`/api/events/delete_class?class_id=${encodeURIComponent(classRecord.id)}`, classRecord.name)}>Delete</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {activeSection === "professors" ? (
        <section className="rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4 md:p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h3 className="text-lg font-bold text-[#111]">Professors</h3>
            {professorMode === "edit" ? <button type="button" onClick={resetProfessorForm} className={secondaryButtonClass}>Cancel Edit</button> : null}
          </div>
          <form onSubmit={handleProfessorSubmit} className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_1fr_auto]">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Name</span>
              <input className={fieldClass} value={professorName} onChange={(event) => setProfessorName(event.target.value)} disabled={!selectedClassId} />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Email</span>
              <input type="email" className={fieldClass} value={professorEmail} onChange={(event) => setProfessorEmail(event.target.value)} disabled={!selectedClassId} placeholder="name@hamilton.edu" />
            </label>
            <div className="flex items-end">
              <button type="submit" className={buttonClass} disabled={!selectedClassId}>{professorMode === "add" ? "Add Professor" : "Save Professor"}</button>
            </div>
          </form>
          <div className="mt-4 space-y-2">
            {professors.length === 0 ? <p className="text-sm text-[#555]">No professors found.</p> : professors.map((professor) => (
              <div key={professor.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#e5e7eb] bg-white p-3">
                <div>
                  <p className="text-sm font-semibold text-[#111]">{professor.name}</p>
                  <p className="text-xs text-[#555]">{professor.email}</p>
                </div>
                <div className="flex gap-2">
                  <button type="button" className={secondaryButtonClass} onClick={() => openAvailability({ linkedId: professor.id, entityName: professor.name, entityKind: "Professor" })}>Availability</button>
                  <button type="button" className={secondaryButtonClass} onClick={() => {
                    setProfessorMode("edit");
                    setProfessorId(professor.id);
                    setProfessorName(professor.name);
                    setProfessorEmail(professor.email);
                  }}>Edit</button>
                  <button type="button" className={dangerButtonClass} onClick={() => void deleteRecord(`/api/events/delete_professor?professor_id=${encodeURIComponent(professor.id)}`, professor.name)}>Delete</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {activeSection === "students" ? (
        <section className="rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4 md:p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h3 className="text-lg font-bold text-[#111]">Students</h3>
            {studentMode === "edit" ? <button type="button" onClick={resetStudentForm} className={secondaryButtonClass}>Cancel Edit</button> : null}
          </div>
          <form onSubmit={handleStudentSubmit} className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_1fr_auto]">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Name</span>
              <input className={fieldClass} value={studentName} onChange={(event) => setStudentName(event.target.value)} disabled={!selectedClassId} />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Email</span>
              <input type="email" className={fieldClass} value={studentEmail} onChange={(event) => setStudentEmail(event.target.value)} disabled={!selectedClassId} placeholder="name@hamilton.edu" />
            </label>
            <div className="flex items-end">
              <button type="submit" className={buttonClass} disabled={!selectedClassId}>{studentMode === "add" ? "Add Student" : "Save Student"}</button>
            </div>
          </form>
          <div className="mt-4 space-y-2">
            {students.length === 0 ? <p className="text-sm text-[#555]">No students found.</p> : students.map((student) => (
              <div key={student.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#e5e7eb] bg-white p-3">
                <div>
                  <p className="text-sm font-semibold text-[#111]">{student.name}</p>
                  <p className="text-xs text-[#555]">{student.email}</p>
                </div>
                <div className="flex gap-2">
                  <button type="button" className={secondaryButtonClass} onClick={() => openAvailability({ linkedId: student.id, entityName: student.name, entityKind: "Student" })}>Availability</button>
                  <button type="button" className={secondaryButtonClass} onClick={() => {
                    setStudentMode("edit");
                    setStudentId(student.id);
                    setStudentName(student.name);
                    setStudentEmail(student.email);
                  }}>Edit</button>
                  <button type="button" className={dangerButtonClass} onClick={() => void deleteRecord(`/api/events/delete_student?student_id=${encodeURIComponent(student.id)}`, student.name)}>Delete</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {activeSection === "presentations" ? (
        <section className="rounded-xl border border-[#e6ecff] bg-[#fdfdff] p-4 md:p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h3 className="text-lg font-bold text-[#111]">Presentations</h3>
            {presentationMode === "edit" ? <button type="button" onClick={resetPresentationForm} className={secondaryButtonClass}>Cancel Edit</button> : null}
          </div>
          <form onSubmit={handlePresentationSubmit} className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <label className="flex flex-col gap-1.5 md:col-span-2">
              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Title</span>
              <input className={fieldClass} value={presentationTitle} onChange={(event) => setPresentationTitle(event.target.value)} disabled={!selectedClassId} />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Duration Minutes</span>
              <input type="number" min={1} className={fieldClass} value={presentationMinutes} onChange={(event) => setPresentationMinutes(event.target.value)} disabled={!selectedClassId} />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Buffer Minutes</span>
              <input type="number" min={0} className={fieldClass} value={presentationBuffer} onChange={(event) => setPresentationBuffer(event.target.value)} disabled={!selectedClassId} />
            </label>
            <label className="flex flex-col gap-1.5 md:col-span-2">
              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Presenting Students</span>
              <select
                multiple
                className={`${fieldClass} min-h-32`}
                value={presentationStudentIdsState}
                onChange={(event) => setPresentationStudentIdsState(selectedValues(event.currentTarget.options))}
                disabled={!selectedClassId}
              >
                {students.map((student) => (
                  <option key={student.id} value={student.id}>{student.name} ({student.email})</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1.5 md:col-span-2">
              <span className="text-xs font-bold uppercase tracking-wide text-[#2d3d7a] md:text-sm">Assigned Professors</span>
              <select
                multiple
                className={`${fieldClass} min-h-32`}
                value={presentationProfessorIdsState}
                onChange={(event) => setPresentationProfessorIdsState(selectedValues(event.currentTarget.options))}
                disabled={!selectedClassId || departmentProfessors.length === 0}
              >
                {departmentProfessors.map((professor) => (
                  <option key={professor.id} value={professor.id}>{professor.name} ({professor.email})</option>
                ))}
              </select>
            </label>
            {presentationMode === "add" ? (
              <label className="flex items-center gap-2 text-sm font-semibold text-[#333] md:col-span-2">
                <input
                  type="checkbox"
                  checked={emailStudentsAfterPresentationAdd}
                  onChange={(event) => setEmailStudentsAfterPresentationAdd(event.target.checked)}
                  disabled={!selectedClassId}
                />
                Send emails after adding presentation
              </label>
            ) : null}
            <div className="md:col-span-2 flex flex-wrap gap-2">
              <button type="submit" className={buttonClass} disabled={!selectedClassId}>{presentationMode === "add" ? "Add Presentation" : "Save Presentation"}</button>
            </div>
          </form>
          <div className="mt-4 space-y-2">
            {presentations.length === 0 ? <p className="text-sm text-[#555]">No presentations found.</p> : presentations.map((presentation) => (
              <div key={presentation.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#e5e7eb] bg-white p-3">
                <div>
                  <p className="text-sm font-semibold text-[#111]">{presentation.title}</p>
                  <p className="text-xs text-[#555]">
                    {presentation.minutes ?? "?"} min, {presentation.buffer ?? 0} min buffer
                    {presentation.presenting_students?.length ? `, ${presentation.presenting_students.map((student) => student.name).join(", ")}` : ""}
                  </p>
                  <p className="text-xs text-[#555]">
                    Assigned professors: {presentation.assigned_professors?.length ? presentation.assigned_professors.map((professor) => professor.name).join(", ") : "All class professors"}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button type="button" className={secondaryButtonClass} onClick={() => {
                    setPresentationMode("edit");
                    setPresentationId(presentation.id);
                    setPresentationTitle(presentation.title);
                    setPresentationMinutes(String(presentation.minutes ?? 20));
                    setPresentationBuffer(String(presentation.buffer ?? 0));
                    setPresentationStudentIdsState(presentationStudentIds(presentation));
                    setPresentationProfessorIdsState(presentationProfessorIds(presentation));
                  }}>Edit</button>
                  <button type="button" className={dangerButtonClass} onClick={() => void deleteRecord(`/api/events/delete_presentation?presentation_id=${encodeURIComponent(presentation.id)}`, presentation.title)}>Delete</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {availabilityTarget ? (
        <AvailabilityEditor
          token={token}
          symposiumId={selectedSymposiumId}
          linkedId={availabilityTarget.linkedId}
          entityName={availabilityTarget.entityName}
          entityKind={availabilityTarget.entityKind}
          onClose={() => setAvailabilityTarget(null)}
        />
      ) : null}
    </div>
  );
}
