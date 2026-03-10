export type AdminTab = "create" | "edit";
export type DepartmentAction = "add" | "edit";
export type FacultyTab = "availability" | "students";
export type StudentTab = "availability" | "preferences";

export type SymposiumOption = {
  id: string;
  name: string;
  created_at?: string;
  symposium_name?: string;
};

export type Timeframe = {
  id: string;
  start_time: string;
  end_time: string;
};

export type TimeframeRecord = {
  id: string;
  start_time: string;
  end_time: string;
  symposium_id: string;
};

export type DepartmentRecord = {
  id: string;
  symposium?: string;
  symposium_id?: string;
  department_name: string;
  department_head_name: string;
  email?: string;
};

export type ClassRecord = {
  id: string;
  department_id: string;
};

export type PresentationRecord = {
  id: string;
  class_id: string;
  title: string;
  presenterNames: string[];
};

export type SymposiumDetails = {
  id: string;
  name: string;
  rooms_available?: number | null;
};

export type DepartmentOption = {
  id: string;
  name: string;
};

export type ProfessorRow = {
  id?: string;
  name: string;
  email: string;
};

export type SavedClass = {
  localId: string;
  classId: string;
  professorIds: string[];
  departmentId: string;
  departmentName: string;
  className: string;
  professors: ProfessorRow[];
};

export type CalendarDay = {
  key: string;
  label: string;
};

export type UploadedStudent = {
  id: string;
  name: string;
};

export type PresentationGroup = {
  id: string;
  studentIds: string[];
  studentNames: string[];
  presentationName: string;
  durationMinutes: string;
};

export type ProfessorOption = {
  id: string;
  name: string;
  classId: string;
};

export type SavedProfessorRequest = {
  id: string;
  professorId: string;
  professorName: string;
  professorEmail: string;
};

export type StudentOption = {
  id: string;
  name: string;
};
