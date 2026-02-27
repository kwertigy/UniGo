import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

type UserMode = 'rider' | 'driver';

interface College {
  id: string;
  name: string;
  short: string;
}

interface User {
  id: string;
  name: string;
  email: string;
  college: College | null;
  ecoScore: number;
  verified: boolean;
  isDriver?: boolean;
  driverVerificationStatus?: 'pending' | 'approved' | 'rejected';
}

interface AppState {
  user: User | null;
  isOnboarded: boolean;
  mode: UserMode;
  
  setUser: (user: User) => void;
  setOnboarded: (value: boolean) => void;
  setMode: (mode: UserMode) => void;
  setCollege: (college: College) => void;
  loadPersistedData: () => Promise<void>;
}

const safeSetItem = async (key: string, value: string) => {
  try {
    if (Platform.OS === 'web') {
      // Use localStorage on web
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem(key, value);
      }
    } else {
      await AsyncStorage.setItem(key, value);
    }
  } catch (e) {
    console.warn('Storage error:', e);
  }
};

const safeGetItem = async (key: string): Promise<string | null> => {
  try {
    if (Platform.OS === 'web') {
      // Use localStorage on web
      if (typeof window !== 'undefined' && window.localStorage) {
        return window.localStorage.getItem(key);
      }
      return null;
    } else {
      return await AsyncStorage.getItem(key);
    }
  } catch (e) {
    console.warn('Storage error:', e);
    return null;
  }
};

export const useAppStore = create<AppState>((set, get) => ({
  user: null,
  isOnboarded: false,
  mode: 'rider',
  
  setUser: (user) => {
    set({ user });
    safeSetItem('user', JSON.stringify(user));
  },
  
  setOnboarded: (value) => {
    set({ isOnboarded: value });
    safeSetItem('isOnboarded', JSON.stringify(value));
  },
  
  setMode: (mode) => {
    set({ mode });
    safeSetItem('mode', mode);
  },
  
  setCollege: (college) => {
    const currentUser = get().user;
    if (currentUser) {
      const updatedUser = { ...currentUser, college };
      set({ user: updatedUser });
      safeSetItem('user', JSON.stringify(updatedUser));
    }
  },
  
  loadPersistedData: async () => {
    try {
      const [userStr, onboardedStr, mode] = await Promise.all([
        safeGetItem('user'),
        safeGetItem('isOnboarded'),
        safeGetItem('mode'),
      ]);
      
      if (userStr) set({ user: JSON.parse(userStr) });
      if (onboardedStr) set({ isOnboarded: JSON.parse(onboardedStr) });
      if (mode) set({ mode: mode as UserMode });
    } catch (error) {
      console.error('Failed to load persisted data:', error);
    }
  },
}));