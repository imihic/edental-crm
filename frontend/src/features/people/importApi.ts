import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch, getTenantSession } from "../../api/client";
import type { components } from "../../api/schema";

type Schemas = components["schemas"];
type PreviewIn = Schemas["PreviewIn"];
export type ImportPreview = Schemas["PreviewOut"];
type CommitIn = Schemas["CommitIn"];
type CommitOut = Schemas["CommitOut"];
type ImportList = Schemas["ImportListOut"];

const importsKey = ["imports"];
const MAX_FILE_BYTES = 5 * 1024 * 1024;

function readBase64(file: File): Promise<string> {
  if (file.size > MAX_FILE_BYTES) {
    return Promise.reject(new ApiError(413, "file_too_large"));
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    const failed = () => reject(new ApiError(0, "file_read_failed"));
    reader.onerror = failed;
    reader.onabort = failed;
    reader.onload = () => {
      const dataUrl = reader.result;
      if (typeof dataUrl !== "string" || !dataUrl.includes(",")) {
        failed();
        return;
      }
      resolve(dataUrl.slice(dataUrl.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}

export function useImportHistory() {
  return useQuery<ImportList, ApiError>({
    queryKey: importsKey,
    queryFn: () => apiFetch<ImportList>("/api/imports"),
    retry: false,
  });
}

export function usePreviewImport() {
  const client = useQueryClient();
  return useMutation<ImportPreview, ApiError, File>({
    mutationFn: async (file) => {
      const tenant = getTenantSession();
      const content = await readBase64(file);
      if (getTenantSession() !== tenant) throw new ApiError(409, "organization_changed");
      const body: PreviewIn = { filename: file.name, content_base64: content };
      return apiFetch<ImportPreview>("/api/imports/patients/preview", { method: "POST", body });
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: importsKey });
    },
  });
}

export function useCommitImport() {
  const client = useQueryClient();
  return useMutation<CommitOut, ApiError, { importId: string; body: CommitIn }>({
    mutationFn: ({ importId, body }) =>
      apiFetch<CommitOut>("/api/imports/patients/" + encodeURIComponent(importId) + "/commit", {
        method: "POST",
        body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: importsKey });
      void client.invalidateQueries({ queryKey: ["patients"] });
    },
    onError: (error) => {
      if (error.code === "already_committed" || error.code === "import_expired") {
        void client.invalidateQueries({ queryKey: importsKey });
      }
    },
  });
}
