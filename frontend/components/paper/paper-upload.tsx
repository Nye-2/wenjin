'use client';

import { useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { Upload, File, X, Loader2, CheckCircle } from 'lucide-react';

interface PaperUploadProps {
  workspaceId: string;
  onUploadComplete?: (paper: UploadedPaper) => void;
  onUploadError?: (error: string) => void;
  maxFileSize?: number; // in bytes
  acceptedTypes?: string[];
}

interface UploadedPaper {
  id: string;
  title: string;
  filename: string;
}

interface UploadingFile {
  file: File;
  progress: number;
  status: 'pending' | 'uploading' | 'success' | 'error';
  error?: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

export function PaperUpload({
  workspaceId,
  onUploadComplete,
  onUploadError,
  maxFileSize = 50 * 1024 * 1024, // 50MB default
  acceptedTypes = ['.pdf', '.tex', '.docx'],
}: PaperUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState<UploadingFile[]>([]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const validateFile = (file: File): string | null => {
    if (file.size > maxFileSize) {
      return `File too large. Maximum size is ${Math.round(maxFileSize / 1024 / 1024)}MB`;
    }

    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!acceptedTypes.includes(ext)) {
      return `Invalid file type. Accepted: ${acceptedTypes.join(', ')}`;
    }

    return null;
  };

  const uploadFile = async (file: File): Promise<void> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('workspace_id', workspaceId);

    try {
      const response = await fetch(`${API_BASE}/papers/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Upload failed');
      }

      const paper = await response.json();
      onUploadComplete?.(paper);
    } catch (error) {
      onUploadError?.(error instanceof Error ? error.message : 'Upload failed');
      throw error;
    }
  };

  const processFiles = async (files: FileList) => {
    const newFiles: UploadingFile[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const validationError = validateFile(file);
      newFiles.push({
        file,
        progress: 0,
        status: validationError ? 'error' : 'pending',
        error: validationError || undefined,
      });
    }

    setUploadingFiles((prev) => [...prev, ...newFiles]);

    // Upload valid files
    for (let i = 0; i < newFiles.length; i++) {
      const uploadingFile = newFiles[i];
      if (uploadingFile.status === 'error') continue;

      const index = uploadingFiles.length + i;
      setUploadingFiles((prev) =>
        prev.map((f, idx) =>
          idx === index ? { ...f, status: 'uploading' } : f
        )
      );

      try {
        // Simulate progress for better UX
        const progressInterval = setInterval(() => {
          setUploadingFiles((prev) =>
            prev.map((f, idx) =>
              idx === index
                ? { ...f, progress: Math.min(f.progress + 10, 90) }
                : f
            )
          );
        }, 100);

        await uploadFile(uploadingFile.file);

        clearInterval(progressInterval);

        setUploadingFiles((prev) =>
          prev.map((f, idx) =>
            idx === index ? { ...f, progress: 100, status: 'success' } : f
          )
        );
      } catch (error) {
        setUploadingFiles((prev) =>
          prev.map((f, idx) =>
            idx === index
              ? {
                  ...f,
                  status: 'error',
                  error: error instanceof Error ? error.message : 'Upload failed',
                }
              : f
          )
        );
      }
    }
  };

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      processFiles(e.dataTransfer.files);
    },
    [workspaceId]
  );

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      processFiles(e.target.files);
    }
  };

  const removeFile = (index: number) => {
    setUploadingFiles((prev) => prev.filter((_, idx) => idx !== index));
  };

  return (
    <div className="space-y-4">
      {/* Drop Zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "border-2 border-dashed rounded-lg p-8 text-center transition-colors",
          isDragging
            ? "border-blue-500 bg-blue-500/10"
            : "border-slate-600 hover:border-slate-500"
        )}
      >
        <Upload className="h-12 w-12 mx-auto mb-4 text-slate-500" />
        <p className="text-lg text-white mb-2">
          Drag and drop papers here
        </p>
        <p className="text-sm text-slate-400 mb-4">
          or click to browse
        </p>
        <input
          type="file"
          multiple
          accept={acceptedTypes.join(',')}
          onChange={handleFileSelect}
          className="hidden"
          id="paper-upload"
        />
        <Button
          type="button"
          variant="outline"
          onClick={() => document.getElementById('paper-upload')?.click()}
        >
          Browse Files
        </Button>
        <p className="text-xs text-slate-500 mt-4">
          Supported: {acceptedTypes.join(', ')} • Max: {Math.round(maxFileSize / 1024 / 1024)}MB
        </p>
      </div>

      {/* Upload Progress */}
      {uploadingFiles.length > 0 && (
        <div className="space-y-2">
          {uploadingFiles.map((file, index) => (
            <Card key={index} className="bg-slate-800/50 border-slate-700">
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <File className="h-8 w-8 text-blue-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-white truncate">{file.file.name}</p>
                    <p className="text-xs text-slate-400">
                      {(file.file.size / 1024 / 1024).toFixed(2)} MB
                    </p>
                    {file.status === 'uploading' && (
                      <Progress value={file.progress} className="h-1 mt-2" />
                    )}
                    {file.status === 'error' && (
                      <p className="text-xs text-red-400 mt-1">{file.error}</p>
                    )}
                  </div>
                  <div className="flex-shrink-0">
                    {file.status === 'pending' && (
                      <span className="text-xs text-slate-400">Pending</span>
                    )}
                    {file.status === 'uploading' && (
                      <Loader2 className="h-5 w-5 animate-spin text-blue-400" />
                    )}
                    {file.status === 'success' && (
                      <CheckCircle className="h-5 w-5 text-green-400" />
                    )}
                    {file.status === 'error' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeFile(index)}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
