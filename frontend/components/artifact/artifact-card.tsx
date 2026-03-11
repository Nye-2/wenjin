'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  FileText,
  BookOpen,
  FlaskConical,
  Lightbulb,
  FileChartColumn,
  MessageSquare,
  History,
  ExternalLink,
  MoreVertical,
} from 'lucide-react';

interface Artifact {
  id: string;
  type: string;
  title?: string;
  content: Record<string, unknown>;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
  created_by_skill?: string;
}

interface ArtifactCardProps {
  artifact: Artifact;
  onClick?: () => void;
  onPreview?: () => void;
  compact?: boolean;
}

const ARTIFACT_TYPE_CONFIG: Record<string, {
  icon: React.ElementType;
  label: string;
  color: string;
}> = {
  research_idea: {
    icon: Lightbulb,
    label: 'Research Idea',
    color: 'bg-amber-500/10 text-amber-600 border-amber-500/30',
  },
  methodology: {
    icon: FlaskConical,
    label: 'Methodology',
    color: 'bg-blue-500/10 text-blue-600 border-blue-500/30',
  },
  framework_outline: {
    icon: FileChartColumn,
    label: 'Framework',
    color: 'bg-purple-500/10 text-purple-600 border-purple-500/30',
  },
  abstract: {
    icon: FileText,
    label: 'Abstract',
    color: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
  },
  introduction: {
    icon: BookOpen,
    label: 'Introduction',
    color: 'bg-cyan-500/10 text-cyan-600 border-cyan-500/30',
  },
  literature_review: {
    icon: BookOpen,
    label: 'Lit Review',
    color: 'bg-indigo-500/10 text-indigo-600 border-indigo-500/30',
  },
  hypothesis: {
    icon: Lightbulb,
    label: 'Hypothesis',
    color: 'bg-orange-500/10 text-orange-600 border-orange-500/30',
  },
  results_analysis: {
    icon: FileChartColumn,
    label: 'Results',
    color: 'bg-pink-500/10 text-pink-600 border-pink-500/30',
  },
  conclusion: {
    icon: MessageSquare,
    label: 'Conclusion',
    color: 'bg-teal-500/10 text-teal-600 border-teal-500/30',
  },
  note: {
    icon: FileText,
    label: 'Note',
    color: 'bg-slate-500/10 text-slate-600 border-slate-500/30',
  },
};

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  draft: { label: 'Draft', color: 'bg-slate-500' },
  in_review: { label: 'Review', color: 'bg-amber-500' },
  approved: { label: 'Approved', color: 'bg-emerald-500' },
  archived: { label: 'Archived', color: 'bg-slate-400' },
};

export function ArtifactCard({
  artifact,
  onClick,
  onPreview,
  compact = false,
}: ArtifactCardProps) {
  const typeConfig = ARTIFACT_TYPE_CONFIG[artifact.type] || {
    icon: FileText,
    label: artifact.type,
    color: 'bg-slate-500/10 text-slate-600 border-slate-500/30',
  };

  const statusConfig = STATUS_CONFIG[artifact.status] || {
    label: artifact.status,
    color: 'bg-slate-500',
  };

  const Icon = typeConfig.icon;

  const getTitle = () => {
    if (artifact.title) return artifact.title;
    if (artifact.content?.title) return artifact.content.title as string;
    return `Untitled ${typeConfig.label}`;
  };

  const getDescription = () => {
    if (artifact.content?.description) {
      return artifact.content.description as string;
    }
    if (artifact.content?.text) {
      const text = artifact.content.text as string;
      return text.length > 100 ? text.slice(0, 100) + '...' : text;
    }
    return null;
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (compact) {
    return (
      <div
        onClick={onClick}
        className={cn(
          "flex items-center gap-3 p-3 rounded-lg border border-[var(--border-default)]",
          "bg-[var(--bg-elevated)] hover:bg-[var(--bg-surface)] cursor-pointer transition-colors"
        )}
      >
        <div className={cn("p-2 rounded-lg", typeConfig.color)}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-[var(--text-primary)] truncate">{getTitle()}</p>
          <p className="text-xs text-[var(--text-muted)]">{typeConfig.label}</p>
        </div>
        <Badge variant="secondary" className={statusConfig.color}>
          v{artifact.version}
        </Badge>
      </div>
    );
  }

  return (
    <Card
      onClick={onClick}
      className={cn(
        "bg-[var(--bg-elevated)] border-[var(--border-default)] hover:border-[var(--accent-primary)]/30",
        "cursor-pointer transition-all hover:shadow-lg"
      )}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className={cn("p-2 rounded-lg", typeConfig.color)}>
              <Icon className="h-5 w-5" />
            </div>
            <div>
              <CardTitle className="text-base text-[var(--text-primary)]">
                {getTitle()}
              </CardTitle>
              <div className="flex items-center gap-2 mt-1">
                <Badge variant="outline" className={cn("text-xs", typeConfig.color)}>
                  {typeConfig.label}
                </Badge>
                <Badge variant="secondary" className={cn("text-xs", statusConfig.color)}>
                  {statusConfig.label}
                </Badge>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {onPreview && (
              <Button
                variant="ghost"
                size="icon"
                onClick={(e) => {
                  e.stopPropagation();
                  onPreview();
                }}
              >
                <ExternalLink className="h-4 w-4" />
              </Button>
            )}
            <Button variant="ghost" size="icon">
              <MoreVertical className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        {getDescription() && (
          <p className="text-sm text-[var(--text-secondary)] line-clamp-2 mb-3">
            {getDescription()}
          </p>
        )}

        <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
          <div className="flex items-center gap-3">
            <span>v{artifact.version}</span>
            {artifact.created_by_skill && (
              <span className="flex items-center gap-1">
                <History className="h-3 w-3" />
                {artifact.created_by_skill}
              </span>
            )}
          </div>
          <span>{formatDate(artifact.updated_at)}</span>
        </div>
      </CardContent>
    </Card>
  );
}
