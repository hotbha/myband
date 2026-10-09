/**
 * The PUT that carries the audio, and the only reason this app uses XHR.
 *
 * `fetch` cannot report upload progress: the body is handed over whole and there is
 * no progress event for it. `XMLHttpRequest` has one on `upload`, and a 200 MiB
 * upload with a frozen bar is a bad experience - so the trade is deliberate and
 * contained in this file.
 *
 * The request goes straight to object storage with the URL the API signed. It never
 * touches this app's server, which is what keeps FastAPI out of the file path.
 */
export type UploadProgress = {
  loaded: number;
  total: number;
};

export type StoragePut = {
  /** The presigned URL from `POST /uploads/presign`. */
  url: string;
  file: File;
  /** The headers that URL's signature covers - the API states which. */
  headers: Record<string, string>;
  onProgress?: (progress: UploadProgress) => void;
  signal?: AbortSignal;
};

export function putFileToStorage({
  url,
  file,
  headers,
  onProgress,
  signal,
}: StoragePut): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();

    request.open("PUT", url, true);

    // Every header here is part of the signature; sending one the API did not sign,
    // or omitting one it did, is what makes storage answer 403.
    for (const [name, value] of Object.entries(headers)) {
      request.setRequestHeader(name, value);
    }

    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onProgress?.({ loaded: event.loaded, total: event.total });
      }
    });

    request.addEventListener("load", () => {
      if (request.status >= 200 && request.status < 300) {
        resolve();
        return;
      }

      reject(new Error(storageMessageFor(request.status)));
    });

    request.addEventListener("error", () => {
      reject(new Error("The upload could not reach storage. Check your connection."));
    });

    request.addEventListener("abort", () => {
      reject(new Error("The upload was cancelled."));
    });

    signal?.addEventListener("abort", () => request.abort(), { once: true });

    request.send(file);
  });
}

/**
 * Storage answers in XML, not in the API's error shape, so the status is turned into
 * something worth reading here rather than shown raw.
 */
function storageMessageFor(status: number): string {
  if (status === 403) {
    return "Storage refused the upload. The link may have expired - start the upload again.";
  }

  if (status === 404) {
    return "Storage has no bucket for this upload. Check the storage configuration.";
  }

  if (status === 413) {
    return "Storage refused the file: it is over the bucket's size limit.";
  }

  return `Storage answered ${status} while uploading the file.`;
}
