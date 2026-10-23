/** Client-side mirror of the backend upload rules (backend/app/services/storage.py). */
export const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md', '.markdown', '.csv', '.html', '.htm']
export const MAX_UPLOAD_MB = 50

export function validateFile(file: File): string | null {
  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!ACCEPTED_EXTENSIONS.includes(ext)) return `Unsupported type ${ext || '(none)'}`
  if (file.size === 0) return 'File is empty'
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `Larger than ${MAX_UPLOAD_MB} MB`
  return null
}
