import { Variants, Transition } from "framer-motion";

// Check for reduced motion preference
const prefersReducedMotion =
  typeof window !== 'undefined'
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false;

// Base transition
export const defaultTransition: Transition = {
  duration: 0.3,
  ease: [0.16, 1, 0.3, 1] as const, // Apple-style easing
};

// Fade in from below
export const fadeInUp: Variants = prefersReducedMotion
  ? { initial: {}, animate: {}, exit: {} }
  : {
      initial: { opacity: 0, y: 20 },
      animate: { opacity: 1, y: 0 },
      exit: { opacity: 0, y: -20 },
    };

// Fade in with scale
export const scaleIn: Variants = prefersReducedMotion
  ? { initial: {}, animate: {}, exit: {} }
  : {
      initial: { opacity: 0, scale: 0.95 },
      animate: { opacity: 1, scale: 1 },
      exit: { opacity: 0, scale: 0.95 },
    };

// Stagger children
export const staggerContainer: Variants = {
  animate: {
    transition: {
      staggerChildren: 0.1,
    },
  },
};

// Card hover effect
export const cardHover = {
  rest: { scale: 1 },
  hover: { scale: 1.02, y: -4 },
};

// Button tap effect
export const buttonTap = {
  scale: 0.98,
};

// Page transition
export const pageTransition: Variants = prefersReducedMotion
  ? { initial: {}, animate: {}, exit: {} }
  : {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
    };

// Slide in from side
export const slideInLeft: Variants = prefersReducedMotion
  ? { initial: {}, animate: {}, exit: {} }
  : {
      initial: { opacity: 0, x: -20 },
      animate: { opacity: 1, x: 0 },
      exit: { opacity: 0, x: -20 },
    };

export const slideInRight: Variants = prefersReducedMotion
  ? { initial: {}, animate: {}, exit: {} }
  : {
      initial: { opacity: 0, x: 20 },
      animate: { opacity: 1, x: 0 },
      exit: { opacity: 0, x: 20 },
    };
