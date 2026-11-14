export interface QuestionDependency {
  id: string;
  not: string;
}

export interface Question {
  id: string;
  question: string;
  // Some rule-built backend questions omit kind; normalizeQuestion defaults those to text.
  kind?: 'text' | 'choice';
  options?: string[];
  depends_on?: QuestionDependency;
  optional?: boolean;
}

export interface ScanResponse {
  session_id: string;
  questions: (Question | string)[];
}

export type Severity = 'Critical' | 'High' | 'Medium' | 'Low';

// One row of the report's gap table, from POST /answer. The backend reads it from the finished report, so both always match.
export interface GapItem {
  name: string;
  severity: Severity;
  evidence: string[];
  group?: string;
  source?: string;
}

// The monthly budget the user gave; monthly_eur is null when no usable budget was given.
export interface Budget {
  monthly_eur: number | null;
  status: string | null;
}

export type AnswerResponse =
  | { status: 'done'; report: string; gaps?: GapItem[]; budget?: Budget; ai_written?: boolean; ai_polish_error?: string | null }
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

// "Where will it run?" option, from POST /targets.
export interface TargetLink {
  label: string;
  url: string;
}

export interface Target {
  id: string;
  label: string;
  provider: string;
  monthly_eur: number | null;
  zone_ha: boolean | null;
  recommended: boolean;
  files: boolean;
  note: string;
  price_note?: string;
  profile: string;
  catch: string;
  drawbacks: string[];
  benefits: string[];
  links: TargetLink[];
  short: string;
  why: string[];
  brief: string;
}

export interface TargetsResponse {
  targets: Target[];
}

// Files and guides, from POST /preview.
export interface DocFile {
  path: string;
  title: string;
  content: string;
}

export interface PreviewFile extends DocFile {
  group: 'basic' | 'cloud';
}

export interface AdviceItem {
  gap: string;
  title: string;
}

export interface SkippedItem {
  gap: string;
  reason: string;
}

export interface PreviewResponse {
  docs: DocFile[];
  files: PreviewFile[];
  advice: AdviceItem[];
  skipped: SkippedItem[];
}

export function normalizeQuestion(q: Question | string): Question {
  return typeof q === 'string' ? { id: q, question: q, kind: 'text' } : { ...q, kind: q.kind ?? 'text' };
}
