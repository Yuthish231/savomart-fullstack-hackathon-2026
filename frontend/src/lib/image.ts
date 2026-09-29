/** Downscale a phone photo to at most `max` px on the long edge and re-encode as JPEG.
 *  A 4 MB camera shot becomes ~200-400 KB, which matters on a weak field connection. */
export async function compressImage(file: File, max = 1600, quality = 0.8): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Could not process photo"))), "image/jpeg", quality),
  );
}
