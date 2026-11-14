export interface QuestionDependency {
  id: string;
  not: string;
}

export interface Question {
  id: string;
  question: string;
  kind: 'text' | 'choice';
  options?: string[];
  depends_on?: QuestionDependency;
  optional?: boolean;
}

export interface ScanResponse {
  session_id: string;
  questions: (Question | string)[];
}

export type AnswerResponse =
  | { status: 'done'; report: string }
  | { status: 'need_more_info'; questions: (Question | string)[] };

export interface UploadFile {
  path: string;
  text: string;
}

export type FileKind = 'send' | 'placeholder';

export interface PickedFile {
  path: string;
  file: File;
  kind: FileKind;
}

export interface PickedFolder {
  root: string;
  files: PickedFile[];
  skipped: Record<string, number>;
  secrets: string[];
  bytes: number;
  tooMany: boolean;
}

export function normalizeQuestion(q: Question | string): Question {
  return typeof q === 'string' ? { id: q, question: q, kind: 'text' } : q;
}
