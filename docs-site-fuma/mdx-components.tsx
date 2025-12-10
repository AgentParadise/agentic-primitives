import defaultMdxComponents from 'fumadocs-ui/mdx';
import type { MDXComponents } from 'mdx/types';
import { HeroScene } from '@/components/HeroScene';
import { Badge } from '@/components/Badge';
import { FeatureCard, FeatureGrid } from '@/components/FeatureCard';
import { GradientButton, ButtonGroup } from '@/components/GradientButton';
import { PrimitiveCard, PrimitiveGrid } from '@/components/PrimitiveCard';

export function getMDXComponents(components?: MDXComponents): MDXComponents {
  return {
    ...defaultMdxComponents,
    HeroScene,
    Badge,
    FeatureCard,
    FeatureGrid,
    GradientButton,
    ButtonGroup,
    PrimitiveCard,
    PrimitiveGrid,
    ...components,
  };
}
