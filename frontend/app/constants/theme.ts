// CampusPool Premium Glass Design System

export const COLORS = {
  // Enhanced Dark Mode
  background: '#1A1A1A',
  backgroundRider: '#0F172A',
  backgroundDriver: '#18181B',
  
  // Pink Mode Overlay
  pinkModeOverlay: 'rgba(255, 20, 147, 0.15)',
  pinkModeFrost: 'rgba(255, 192, 203, 0.1)',
  
  cardSurface: '#1C1C1E',
  cardBorder: '#2C2C2E',
  cardStroke: '#3A3A3C',
  glassWhiteBorder: 'rgba(255, 255, 255, 0.5)',
  elevated: '#2C2C2E',
  
  // Primary Accent
  orange: '#FF7F50',
  orangeLight: '#FFB199',
  orangeGlow: 'rgba(255, 127, 80, 0.3)',
  orangeDark: '#FF6B35',
  
  // Pink Pool
  pinkPool: '#FF1493',
  pinkPoolGlow: 'rgba(255, 20, 147, 0.4)',
  pinkPoolBorder: 'rgba(255, 192, 203, 0.6)',
  roseGlow: 'rgba(255, 182, 193, 0.3)',
  
  // Map Colors
  neonBlue: '#00D9FF',
  neonBlueGlow: 'rgba(0, 217, 255, 0.6)',
  dottedWhite: 'rgba(255, 255, 255, 0.4)',
  
  // Text (Stark White)
  white: '#FFFFFF',
  textPrimary: '#FFFFFF',
  textSecondary: '#A8A8A8',
  textTertiary: '#636366',
  
  // Functional
  success: '#32D74B',
  warning: '#FFD60A',
  error: '#FF453A',
  blue: '#0A84FF',
  gold: '#FFD700',
  
  // Additional Colors
  electricBlue: '#00D9FF',
  emeraldGreen: '#32D74B',
  pink: '#FF69B4',
  
  // Glassmorphism
  glassDark: 'rgba(28, 28, 30, 0.15)',
  glassLight: 'rgba(255, 255, 255, 0.1)',
  blur: 'rgba(0, 0, 0, 0.3)',
  
  // Gradients
  meshStart: '#0A0A0A',
  meshEnd: '#1A1A1D',
  
  // Alpha variations
  whiteAlpha40: 'rgba(255, 255, 255, 0.4)',
  whiteAlpha60: 'rgba(255, 255, 255, 0.6)',
  whiteAlpha80: 'rgba(255, 255, 255, 0.8)',
  whiteAlpha90: 'rgba(255, 255, 255, 0.9)',
  
  // High contrast colors for Driver dashboard
  driverText: '#FFFFFF',
  driverTextSecondary: '#E0E0E0',
  driverTextMuted: '#B0B0B0',
  
  // Slate colors for backgrounds
  slate700: '#334155',
  slate800: '#1E293B',
  slate900: '#0F172A',
};

export const SPACING = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const BORDER_RADIUS = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  pill: 100,
  full: 9999,
};

export const FONTS = {
  family: '-apple-system, SF Pro Display, Inter, system-ui',
  sizes: {
    xs: 11,
    sm: 13,
    md: 15,
    lg: 17,
    xl: 22,
    xxl: 28,
    huge: 34,
  },
  weights: {
    regular: '400',
    medium: '500',
    semibold: '600',
    bold: '700',
    heavy: '800',
  },
};

export const COLLEGES = [
  { id: '1', name: 'New Horizon College of Engineering (NHCE)', short: 'NHCE', department: 'Computer Science' },
  { id: '2', name: 'RV College of Engineering (RVCE)', short: 'RVCE', department: 'Electronics' },
  { id: '3', name: 'PES University (PESU)', short: 'PESU', department: 'Information Science' },
  { id: '4', name: 'BMS College of Engineering (BMSCE)', short: 'BMSCE', department: 'Mechanical' },
  { id: '5', name: 'MS Ramaiah Institute of Technology', short: 'MSRIT', department: 'Civil' },
];

export const SHADOW_STYLES = {
  subtle: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 3,
  },
  card: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 12,
    elevation: 6,
  },
  elevated: {
    shadowColor: COLORS.orange,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.3,
    shadowRadius: 16,
    elevation: 10,
  },
  glow: {
    shadowColor: COLORS.orange,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 20,
    elevation: 12,
  },
  pinkGlow: {
    shadowColor: COLORS.pinkPool,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.6,
    shadowRadius: 24,
    elevation: 14,
  },
};