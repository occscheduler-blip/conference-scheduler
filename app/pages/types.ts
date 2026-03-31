export type AdminTab = "create" | "edit" | "admins";
export type DepartmentAction = "add" | "edit";
// Tab state for the faculty/professor page
export type FacultyTab = "availability" | "students";
// Tab state for the student page
export type StudentTab = "availability" | "preferences";

// A symposium entry as returned by the API, used in dropdowns/selects
export type SymposiumOption = {
  id: string;
  name: string;
  created_at?: string;
  symposium_name?: string;
};

// A time slot with a start and end time (display use, no symposium reference)
export type Timeframe = {
  id: string;
  start_time: string;
  end_time: string;
};

// A time slot tied to a specific symposium (used when fetching from the DB)
export type TimeframeRecord = {
  id: string;
  start_time: string;
  end_time: string;
  symposium_id: string;
};

// A department as stored in the database
export type DepartmentRecord = {
  id: string;
  symposium?: string;
  symposium_id?: string;
  department_name: string;
  department_head_name: string;
  email?: string;
};

// A class (course) linked to a department
export type ClassRecord = {
  id: string;
  department_id: string;
};

// A presentation linked to a class, with a title and list of presenter names
export type PresentationRecord = {
  id: string;
  class_id: string;
  title: string;
  presenterNames: string[];
};

// Core details about a symposium, including optional room count
export type SymposiumDetails = {
  id: string;
  name: string;
  rooms_available?: number | null;
};

// A department entry used in dropdowns/selects
export type DepartmentOption = {
  id: string;
  name: string;
};

// A professor/faculty member with optional DB id
export type ProfessorRow = {
  id?: string;
  name: string;
  email: string;
};

// A class that has been saved locally during the admin create flow
export type SavedClass = {
  localId: string;
  classId: string;
  professorIds: string[];
  departmentId: string;
  departmentName: string;
  className: string;
  professors: ProfessorRow[];
};

// A single day entry used for availability calendar display
export type CalendarDay = {
  key: string;
  label: string;
};

// A student that has been uploaded via CSV or form
export type UploadedStudent = {
  id: string;
  name: string;
};

// A group of students presenting together, with a name and duration
export type PresentationGroup = {
  id: string;
  studentIds: string[];
  studentNames: string[];
  presentationName: string;
  durationMinutes: string;
  bufferMinutes: string;
};

// A professor entry used in dropdowns, scoped to a specific class
export type ProfessorOption = {
  id: string;
  name: string;
  classId: string;
};

// A saved request linking a professor to an event, used in student preference forms
export type SavedProfessorRequest = {
  id: string;
  professorId: string;
  professorName: string;
  professorEmail: string;
};

// A student entry used in dropdowns/selects
export type StudentOption = {
  id: string;
  name: string;
};
