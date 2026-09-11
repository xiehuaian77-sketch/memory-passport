import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function confidenceLabel(c: number): string {
  if (c >= 0.9) return '高可信';
  if (c >= 0.6) return '中可信';
  return '低可信';
}

export function confidenceColor(c: number): string {
  if (c >= 0.9) return 'text-green-400';
  if (c >= 0.6) return 'text-yellow-400';
  return 'text-red-400';
}
