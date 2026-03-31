/**
 * Prompt editor component
 */

import { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';

export interface PromptEditorProps {
  name: string;
  content: string;
  description?: string;
  onSave?: (content: string) => Promise<void>;
  loading?: boolean;
  className?: string;
}

function PromptEditor({
  name,
  content,
  description,
  onSave,
  loading,
  className,
}: PromptEditorProps) {
  const [editedContent, setEditedContent] = useState(content);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    setEditedContent(content);
    setHasChanges(false);
  }, [content]);

  const handleChange = (value: string) => {
    setEditedContent(value);
    setHasChanges(value !== content);
  };

  const handleSave = async () => {
    if (onSave) {
      await onSave(editedContent);
      setHasChanges(false);
    }
  };

  const handleReset = () => {
    setEditedContent(content);
    setHasChanges(false);
  };

  // Count lines and characters
  const lines = editedContent.split('\n').length;
  const chars = editedContent.length;

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>{name}</CardTitle>
            {description && (
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{description}</p>
            )}
          </div>
          {hasChanges && (
            <span className="text-sm text-amber-600 dark:text-amber-400">Unsaved changes</span>
          )}
        </div>
      </CardHeader>

      <CardContent>
        <textarea
          value={editedContent}
          onChange={(e) => handleChange(e.target.value)}
          className={cn(
            'min-h-[300px] w-full rounded-lg border border-gray-200 bg-gray-50 p-4 font-mono text-sm',
            'focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500',
            'dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100'
          )}
          spellCheck={false}
        />
        <div className="mt-2 flex justify-between text-xs text-gray-500">
          <span>
            {lines} lines, {chars} characters
          </span>
          <span>Markdown supported</span>
        </div>
      </CardContent>

      <CardFooter className="gap-2">
        <Button variant="ghost" onClick={handleReset} disabled={!hasChanges || loading}>
          Reset
        </Button>
        <Button onClick={handleSave} disabled={!hasChanges} loading={loading}>
          Save Changes
        </Button>
      </CardFooter>
    </Card>
  );
}

export { PromptEditor };
