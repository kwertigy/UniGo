import React, { useEffect, useState, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  SafeAreaView,
  TouchableOpacity,
  StatusBar,
  Animated,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useAppStore } from './store/appStore';
import { OnboardingModal } from './components/OnboardingModal';
import { RiderDashboard } from './components/RiderDashboard';
import { DriverDashboard } from './components/DriverDashboard';
import { PaymentModal } from './components/PaymentModal';
import { VibeCheckModal } from './components/VibeCheckModal';
import { COLORS, SPACING, FONTS, BORDER_RADIUS, SHADOW_STYLES } from './constants/theme';
import { SubscriptionTier, Rating } from './types';

export default function Index() {
  const { user, isOnboarded, mode, setOnboarded, setMode, loadPersistedData } = useAppStore();
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [showPayment, setShowPayment] = useState(false);
  const [selectedTier, setSelectedTier] = useState<SubscriptionTier | null>(null);
  const [showVibeCheck, setShowVibeCheck] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const toggleAnim = useRef(new Animated.Value(0)).current;
  const bgColorAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    loadPersistedData().then(() => {
      setIsLoading(false);
    });
  }, []);

  // Show onboarding after loading completes if not onboarded
  useEffect(() => {
    if (!isLoading && !isOnboarded) {
      setTimeout(() => setShowOnboarding(true), 300);
    }
  }, [isLoading, isOnboarded]);

  useEffect(() => {
    Animated.spring(toggleAnim, {
      toValue: mode === 'rider' ? 0 : 1,
      friction: 8,
      tension: 40,
      useNativeDriver: false,
    }).start();
    
    Animated.timing(bgColorAnim, {
      toValue: mode === 'rider' ? 0 : 1,
      duration: 400,
      useNativeDriver: false,
    }).start();
  }, [mode]);

  const handleOnboardingComplete = () => {
    setShowOnboarding(false);
    setOnboarded(true);
  };

  const handleSubscribe = (tier: SubscriptionTier) => {
    setSelectedTier(tier);
    setShowPayment(true);
  };

  const handlePaymentSuccess = () => {
    setShowPayment(false);
    setSelectedTier(null);
  };

  const handleRatingSubmit = (rating: Rating) => {
    console.log('Rating submitted:', rating);
    setShowVibeCheck(false);
  };

  const toggleLeft = toggleAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['4%', '52%'],
  });

  const backgroundColor = bgColorAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [COLORS.backgroundRider, COLORS.backgroundDriver],
  });

  // Show loading screen while checking persisted data
  if (isLoading) {
    return (
      <View style={[styles.container, { backgroundColor: COLORS.background, justifyContent: 'center', alignItems: 'center' }]}>
        <Ionicons name="car-sport" size={64} color={COLORS.orange} />
        <Text style={{ color: COLORS.white, marginTop: 16, fontSize: 18 }}>Loading...</Text>
      </View>
    );
  }

  return (
    <Animated.View style={[styles.container, { backgroundColor }]}>
      <SafeAreaView style={styles.safeArea}>
        <StatusBar barStyle="light-content" backgroundColor="transparent" translucent />
        
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.logo}>
            <View style={styles.logoIcon}>
              <Ionicons name="car-sport" size={24} color={COLORS.orange} />
            </View>
            <View>
              <Text style={styles.logoText}>CampusPool</Text>
              {user?.college && (
                <Text style={styles.collegeText}>@ {user.college.short}</Text>
              )}
            </View>
          </View>
        </View>

        {/* Enhanced Mode Toggle */}
        <View style={styles.toggleContainer}>
          <View style={[styles.togglePill, SHADOW_STYLES.card]}>
            <Animated.View
              style={[
                styles.toggleIndicator,
                {
                  left: toggleLeft,
                  backgroundColor: COLORS.orange,
                },
                SHADOW_STYLES.glow,
              ]}
            />
            <TouchableOpacity
              style={styles.toggleButton}
              onPress={() => setMode('rider')}
              activeOpacity={0.7}
            >
              <Ionicons 
                name="person" 
                size={18} 
                color={mode === 'rider' ? COLORS.white : COLORS.textSecondary} 
              />
              <Text style={[styles.toggleText, mode === 'rider' && styles.toggleTextActive]}>
                Rider
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.toggleButton}
              onPress={() => setMode('driver')}
              activeOpacity={0.7}
            >
              <Ionicons 
                name="car" 
                size={18} 
                color={mode === 'driver' ? COLORS.white : COLORS.textSecondary} 
              />
              <Text style={[styles.toggleText, mode === 'driver' && styles.toggleTextActive]}>
                Driver
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Dashboard Content */}
        <View style={styles.content}>
          {mode === 'rider' ? (
            <RiderDashboard onSubscribe={handleSubscribe} />
          ) : (
            <DriverDashboard />
          )}
        </View>

        {/* Enhanced Floating Action Button */}
        <TouchableOpacity
          style={[styles.fab, SHADOW_STYLES.glow]}
          onPress={() => setShowVibeCheck(true)}
          activeOpacity={0.85}
        >
          <LinearGradient
            colors={[COLORS.orange, COLORS.orangeDark]}
            style={styles.fabGradient}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
          >
            <Ionicons name="star" size={24} color={COLORS.white} />
          </LinearGradient>
        </TouchableOpacity>

        {/* Modals */}
        <OnboardingModal
          visible={showOnboarding}
          onComplete={handleOnboardingComplete}
        />
        <PaymentModal
          visible={showPayment}
          tier={selectedTier}
          onSuccess={handlePaymentSuccess}
          onClose={() => setShowPayment(false)}
        />
        <VibeCheckModal
          visible={showVibeCheck}
          driverName="Rahul"
          onSubmit={handleRatingSubmit}
          onClose={() => setShowVibeCheck(false)}
        />
      </SafeAreaView>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  safeArea: {
    flex: 1,
  },
  header: {
    paddingHorizontal: SPACING.lg,
    paddingVertical: SPACING.md,
  },
  logo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.md,
  },
  logoIcon: {
    width: 48,
    height: 48,
    borderRadius: BORDER_RADIUS.md,
    backgroundColor: COLORS.cardSurface,
    borderWidth: 1,
    borderColor: COLORS.cardStroke,
    justifyContent: 'center',
    alignItems: 'center',
  },
  logoText: {
    fontSize: FONTS.sizes.xl,
    fontWeight: FONTS.weights.heavy,
    color: COLORS.textPrimary,
    letterSpacing: -0.5,
  },
  collegeText: {
    fontSize: FONTS.sizes.sm,
    color: COLORS.textSecondary,
    fontWeight: FONTS.weights.semibold,
  },
  toggleContainer: {
    paddingHorizontal: SPACING.lg,
    marginBottom: SPACING.lg,
  },
  togglePill: {
    flexDirection: 'row',
    backgroundColor: COLORS.cardSurface,
    borderRadius: BORDER_RADIUS.pill,
    padding: 4,
    position: 'relative',
    borderWidth: 1,
    borderColor: COLORS.cardStroke,
  },
  toggleIndicator: {
    position: 'absolute',
    width: '46%',
    height: '86%',
    borderRadius: BORDER_RADIUS.pill,
    top: '7%',
  },
  toggleButton: {
    flex: 1,
    flexDirection: 'row',
    gap: SPACING.xs,
    paddingVertical: SPACING.sm + 2,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1,
  },
  toggleText: {
    fontSize: FONTS.sizes.md,
    color: COLORS.textSecondary,
    fontWeight: FONTS.weights.bold,
  },
  toggleTextActive: {
    color: COLORS.white,
  },
  content: {
    flex: 1,
  },
  fab: {
    position: 'absolute',
    bottom: SPACING.xl,
    right: SPACING.xl,
    width: 56,
    height: 56,
    borderRadius: BORDER_RADIUS.full,
    overflow: 'hidden',
  },
  fabGradient: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
  },
});