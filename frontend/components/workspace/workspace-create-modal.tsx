'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2, Plus } from 'lucide-react';

interface WorkspaceCreateModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (workspace: {
    name: string;
    type: string;
    discipline?: string;
    description?: string;
  }) => Promise<void>;
}

const WORKSPACE_TYPES = [
  { value: 'sci', label: 'Scientific Research' },
  { value: 'thesis', label: 'Thesis/Dissertation' },
  { value: 'proposal', label: 'Research Proposal' },
  { value: 'grant', label: 'Grant Application' },
  { value: 'literature_review', label: 'Literature Review' },
] as const;

const DISCIPLINES = [
  'computer_science',
  'mathematics',
  'physics',
  'chemistry',
  'biology',
  'medicine',
  'engineering',
  'economics',
  'psychology',
  'sociology',
  'political_science',
  'history',
  'philosophy',
  'linguistics',
  'other',
] as const;

export function WorkspaceCreateModal({
  open,
  onOpenChange,
  onCreate,
}: WorkspaceCreateModalProps) {
  const [name, setName] = useState('');
  const [type, setType] = useState<string>('sci');
  const [discipline, setDiscipline] = useState<string>('');
  const [description, setDescription] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!name.trim()) {
      setError('Workspace name is required');
      return;
    }

    setIsLoading(true);
    try {
      await onCreate({
        name: name.trim(),
        type,
        discipline: discipline || undefined,
        description: description.trim() || undefined,
      });
      // Reset form
      setName('');
      setType('sci');
      setDiscipline('');
      setDescription('');
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create workspace');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-slate-800 border-slate-700 text-white">
        <DialogHeader>
          <DialogTitle>Create New Workspace</DialogTitle>
          <DialogDescription className="text-slate-400">
            Set up a new workspace for your research project
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit}>
          <div className="space-y-4 py-4">
            {error && (
              <div className="text-sm text-red-400 bg-red-900/30 p-3 rounded-md">
                {error}
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="name">Workspace Name</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My Research Project"
                className="bg-slate-900/50 border-slate-600"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="type">Workspace Type</Label>
              <Select value={type} onValueChange={setType}>
                <SelectTrigger className="bg-slate-900/50 border-slate-600">
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700">
                  {WORKSPACE_TYPES.map((t) => (
                    <SelectItem
                      key={t.value}
                      value={t.value}
                      className="text-white hover:bg-slate-700"
                    >
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="discipline">Discipline (optional)</Label>
              <Select value={discipline} onValueChange={setDiscipline}>
                <SelectTrigger className="bg-slate-900/50 border-slate-600">
                  <SelectValue placeholder="Select discipline" />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700">
                  {DISCIPLINES.map((d) => (
                    <SelectItem
                      key={d}
                      value={d}
                      className="text-white hover:bg-slate-700"
                    >
                      {d.replace('_', ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description (optional)</Label>
              <Input
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Brief description of your research"
                className="bg-slate-900/50 border-slate-600"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Plus className="mr-2 h-4 w-4" />
                  Create Workspace
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
