export type TopicStatus = "pending" | "generated" | "ready_to_publish" | "done";

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
  tts_dialogue: Array<Record<string, string>>;
  canonical_script_id: number | null;
  publish_job_id: number | null;
  published_at: string | null;
  status_detail: string | null;
  playlist_name: string | null;
  media: MediaInfo;
}

export type PlatformUploadStatus = "pending" | "partial" | "done";

export interface MediaInfo {
  artifact: string | null;
  audio: string | null;
  audio_mtime: number | null;
  video: string | null;
  images: string[];
  scene_images: SceneImageInfo[];
  subtitles: { ass: string | null; srt_nl: string | null; srt_en: string | null };
  shorts: ShortInfo[];
  platform_status: {
    instagram: PlatformUploadStatus;
    tiktok: PlatformUploadStatus;
    youtube_shorts: PlatformUploadStatus;
    facebook: PlatformUploadStatus;
  };
  checkpoint: string | null;
}

export interface SceneImageInfo {
  scene: number;
  description: string;
  trigger: string;
  prompt: string;
  prompt_9x16: string;
  image_16x9: string | null;
  image_9x16: string | null;
}

export interface ShortInfo {
  scene: string | null;
  description: string | null;
  image_path?: string | null;
  video_file: string | null;
  reel_id: string | null;
  container_id: string | null;
  permalink: string | null;
  draft: boolean;
  reel_scheduled_at: string | null;
  instagram_scheduled_at: string | null;
  tiktok_scheduled_at: string | null;
  facebook_scheduled_at: string | null;
  youtube: { short_video_id?: string; [key: string]: unknown } | null;
  tiktok: { publish_id?: string; [key: string]: unknown } | null;
  instagram: { reel_id?: string; permalink?: string; [key: string]: unknown } | null;
  facebook: { post_id?: string; video_id?: string; manually_marked?: boolean; [key: string]: unknown } | null;
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

export interface PlatformShortStatus {
  scene: number;
  description: string | null;
  video_file: string | null;
  reel_scheduled_at: string | null;
  youtube: {
    short_video_id: string | null;
    url: string | null;
    playlist_name: string | null;
  } | null;
  instagram: {
    reel_id: string | null;
    permalink: string | null;
    manually_marked: boolean;
    scheduled_at: string | null;
  } | null;
  tiktok: {
    publish_id: string | null;
    scheduled_at: string | null;
  } | null;
  facebook: {
    post_id: string | null;
    video_id: string | null;
    manually_marked: boolean;
    scheduled_at: string | null;
  } | null;
}

export interface PlatformStatusItem {
  topic_id: string;
  title: string;
  level: string;
  category: string;
  youtube: {
    video_id: string | null;
    url: string | null;
    status: string;
    scheduled_at: string | null;
    published_at: string | null;
  };
  shorts: PlatformShortStatus[];
}

export interface PlatformCount {
  published: number;
  scheduled: number;
  pending: number;
}

export interface PlatformStatusResponse {
  counts: Record<string, PlatformCount>;
  items: PlatformStatusItem[];
}
