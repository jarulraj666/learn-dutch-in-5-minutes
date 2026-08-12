export type TopicStatus = "pending" | "generated" | "done";

export interface Topic {
  id: string;
  track: string;
  title_hint: string;
  level: string;
  category: string;
  status: TopicStatus;
  order_index: number;
  last_used_at: string | null;
  use_count: number;
  script_title: string | null;
  script_created_at: string | null;
  youtube_video_id: string | null;
  scheduled_at: string | null;
  artifact_path: string | null;
  video_file_path: string | null;
  publish_status: string | null;
}

export interface TopicDetail extends Topic {
  script: Record<string, unknown> | null;
  canonical_script_id: number | null;
  publish_job_id: number | null;
  published_at: string | null;
  status_detail: string | null;
  playlist_name: string | null;
  media: MediaInfo;
}

export interface MediaInfo {
  artifact: string | null;
  audio: string | null;
  video: string | null;
  images: string[];
  subtitles: { ass: string | null; srt_nl: string | null; srt_en: string | null };
  shorts: ShortInfo[];
  checkpoint: string | null;
}

export interface ShortInfo {
  scene: string | null;
  description: string | null;
  video_file: string | null;
  reel_id: string | null;
  container_id: string | null;
  permalink: string | null;
  draft: boolean;
}

export interface Stats {
  total: number;
  by_status: Record<string, number>;
  by_level: Record<string, number>;
  by_category: Record<string, number>;
  recent: Topic[];
}

export interface PipelineJob {
  job_id: string;
  args: string[];
  started_at: string;
  status: "running" | "done" | "failed" | "aborted";
  exit_code: number | null;
  log?: string[];
}

export interface PublishJob {
  id: number;
  topic_id: string;
  title_hint: string;
  level: string;
  category: string;
  script_title: string | null;
  playlist_track: string;
  playlist_name: string | null;
  scheduled_at: string;
  status: string;
  youtube_video_id: string | null;
  artifact_path: string | null;
  published_at: string | null;
  status_detail: string | null;
}
