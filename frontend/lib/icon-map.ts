import {
  BookOpen,
  Code,
  Compass,
  FileText,
  FlaskConical,
  Image,
  Lightbulb,
  List,
  Microscope,
  Package,
  Pen,
  Search,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export const iconMap: Record<string, LucideIcon> = {
  search: Search,
  "book-open": BookOpen,
  "file-text": FileText,
  list: List,
  pen: Pen,
  image: Image,
  package: Package,
  microscope: Microscope,
  "shield-check": ShieldCheck,
  compass: Compass,
  "flask-conical": FlaskConical,
  lightbulb: Lightbulb,
  code: Code,
};

export const defaultIcon: LucideIcon = Search;

export function resolveIcon(name: string | undefined | null): LucideIcon {
  if (!name) return defaultIcon;
  return iconMap[name] ?? defaultIcon;
}
