import { Bot, Cloud, Code2, Contact, Rocket, ScanSearch, ShieldCheck, Smartphone, Workflow, Wrench } from 'lucide-react';
import type { Service } from '@/data/services';

const icons = { Bot, Cloud, Code2, Contact, Rocket, ScanSearch, ShieldCheck, Smartphone, Workflow, Wrench };

export default function ServiceIcon({ name, className }: { name: Service['icon']; className?: string }) {
  const Icon = icons[name];
  return <Icon className={className} aria-hidden />;
}
