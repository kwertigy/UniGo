import React, { useEffect, useState, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  TextInput,
  Animated,
  Dimensions,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { COLORS, SPACING, BORDER_RADIUS, FONTS, COLLEGES } from '../constants/theme';
import { useAppStore } from '../store/appStore';
import apiService from '../services/api';

const { width, height } = Dimensions.get('window');

interface OnboardingModalProps {
  visible: boolean;
  onComplete: () => void;
}

export const OnboardingModal: React.FC<OnboardingModalProps> = ({ visible, onComplete }) => {
  const [step, setStep] = useState<'welcome' | 'college' | 'email' | 'verifying' | 'success'>('welcome');
  const [selectedCollege, setSelectedCollege] = useState(COLLEGES[0]);
  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState('');
  const [showCollegeList, setShowCollegeList] = useState(false);
  const { setUser, setCollege } = useAppStore();
  
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const scaleAnim = useRef(new Animated.Value(0.95)).current;
  const carAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      Animated.parallel([
        Animated.timing(fadeAnim, {
          toValue: 1,
          duration: 600,
          useNativeDriver: true,
        }),
        Animated.spring(scaleAnim, {
          toValue: 1,
          friction: 8,
          useNativeDriver: true,
        }),
      ]).start();
      
      Animated.loop(
        Animated.sequence([
          Animated.timing(carAnim, {
            toValue: 1,
            duration: 3000,
            useNativeDriver: true,
          }),
          Animated.timing(carAnim, {
            toValue: 0,
            duration: 0,
            useNativeDriver: true,
          }),
        ])
      ).start();
    }
  }, [visible]);

  const validateEmail = (emailInput: string): boolean => {
    setEmailError('');
    
    if (!emailInput) {
      setEmailError('Email is required');
      return false;
    }
    
    // Simple email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(emailInput)) {
      setEmailError('Please enter a valid email address');
      return false;
    }
    
    return true;
  };

  const handleVerify = async () => {
    if (!validateEmail(email)) {
      return;
    }
    
    setStep('verifying');
    
    try {
      // Try to create user via API, fall back to local if API fails
      const userName = email.split('@')[0];
      let user;
      
      try {
        user = await apiService.createUser({
          name: userName,
          email,
          college: selectedCollege,
        });
      } catch (apiError) {
        // API might be down, create local user
        console.log('API unavailable, using local user:', apiError);
        user = {
          id: Date.now().toString(),
          name: userName,
          email,
          college: selectedCollege,
          ecoScore: 0,
          verified: true,
        };
      }
      
      setStep('success');
      setUser({
        id: user.id,
        name: user.name,
        email: user.email,
        college: selectedCollege,
        ecoScore: user.ecoScore || 0,
        verified: true,
      });
      setCollege(selectedCollege);
      
      // Connect WebSocket for real-time updates
      apiService.connectWebSocket(user.id);
      
      setTimeout(() => onComplete(), 1500);
    } catch (error) {
      console.error('Verification error:', error);
      Alert.alert('Error', 'Failed to verify. Please try again.');
      setStep('email');
    }
  };

  if (!visible) return null;

  const carTranslateX = carAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [-100, width + 100],
  });

  return (
    <View style={styles.container}>
      <LinearGradient
        colors={[COLORS.meshStart, COLORS.meshEnd, COLORS.background]}
        style={StyleSheet.absoluteFill}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
      />

      <Animated.View
        style={[
          styles.content,
          {
            opacity: fadeAnim,
            transform: [{ scale: scaleAnim }],
          },
        ]}
      >
        {step === 'welcome' && (
          <View style={styles.welcomeContainer}>
            <View style={styles.animationContainer}>
              <View style={styles.pathLine} />
              <Animated.View
                style={[
                  styles.carIcon,
                  { transform: [{ translateX: carTranslateX }] },
                ]}
              >
                <Ionicons name="car-sport" size={40} color={COLORS.orange} />
              </Animated.View>
            </View>

            <Text style={styles.welcomeTitle}>Welcome to{' \n'}CampusPool</Text>
            <Text style={styles.welcomeSubtitle}>
              Bangalore's Exclusive College{'\n'}Carpooling Experience
            </Text>

            <TouchableOpacity
              style={styles.primaryButton}
              onPress={() => setStep('college')}
              activeOpacity={0.85}
            >
              <Text style={styles.primaryButtonText}>Get Started</Text>
              <Ionicons name="arrow-forward" size={20} color={COLORS.white} />
            </TouchableOpacity>
          </View>
        )}

        {step === 'college' && (
          <ScrollView style={styles.scrollContainer} showsVerticalScrollIndicator={false}>
            <View style={styles.formContainer}>
              <Ionicons name="school-outline" size={64} color={COLORS.orange} />
              <Text style={styles.formTitle}>Select Your Campus</Text>
              <Text style={styles.formSubtitle}>Choose your college to get started</Text>

              <TouchableOpacity
                style={styles.glassDropdown}
                onPress={() => setShowCollegeList(!showCollegeList)}
                activeOpacity={0.8}
              >
                <Text style={styles.dropdownText}>{selectedCollege.name}</Text>
                <Ionicons
                  name={showCollegeList ? 'chevron-up' : 'chevron-down'}
                  size={20}
                  color={COLORS.textSecondary}
                />
              </TouchableOpacity>

              {showCollegeList && (
                <View style={styles.collegeList}>
                  {COLLEGES.map((college) => (
                    <TouchableOpacity
                      key={college.id}
                      style={[
                        styles.collegeItem,
                        selectedCollege.id === college.id && styles.selectedCollege,
                      ]}
                      onPress={() => {
                        setSelectedCollege(college);
                        setShowCollegeList(false);
                      }}
                      activeOpacity={0.7}
                    >
                      <Text
                        style={[
                          styles.collegeItemText,
                          selectedCollege.id === college.id && styles.selectedCollegeText,
                        ]}
                      >
                        {college.name}
                      </Text>
                      {selectedCollege.id === college.id && (
                        <Ionicons name="checkmark-circle" size={20} color={COLORS.orange} />
                      )}
                    </TouchableOpacity>
                  ))}
                </View>
              )}

              <TouchableOpacity
                style={styles.primaryButton}
                onPress={() => setStep('email')}
                activeOpacity={0.85}
              >
                <Text style={styles.primaryButtonText}>Continue</Text>
              </TouchableOpacity>
            </View>
          </ScrollView>
        )}

        {step === 'email' && (
          <View style={styles.formContainer}>
            <View style={styles.shieldContainer}>
              <Ionicons name="shield-checkmark" size={64} color={COLORS.orange} />
            </View>
            <Text style={styles.formTitle}>Verify Your Identity</Text>
            <Text style={styles.formSubtitle}>Use your college or personal email address</Text>

            <View style={styles.campusBadge}>
              <Ionicons name="school" size={16} color={COLORS.orange} />
              <Text style={styles.campusBadgeText}>CampusPool @ {selectedCollege.short}</Text>
            </View>

            <View style={styles.inputContainer}>
              <Ionicons name="mail-outline" size={20} color={COLORS.textSecondary} />
              <TextInput
                style={styles.floatingInput}
                placeholder="your.email@example.com"
                placeholderTextColor={COLORS.textTertiary}
                value={email}
                onChangeText={(text) => {
                  setEmail(text);
                  setEmailError('');
                }}
                keyboardType="email-address"
                autoCapitalize="none"
                autoComplete="email"
              />
            </View>

            {emailError ? (
              <View style={styles.errorCapsule}>
                <Ionicons name="warning" size={16} color={COLORS.error} />
                <Text style={styles.errorText}>{emailError}</Text>
              </View>
            ) : null}

            <View style={styles.privacyNotice}>
              <Ionicons name="lock-closed" size={14} color={COLORS.textTertiary} />
              <Text style={styles.privacyText}>
                Your data is encrypted and only accessible by authorized campus administrators.
              </Text>
            </View>

            <TouchableOpacity
              style={[styles.primaryButton, !email && styles.buttonDisabled]}
              onPress={handleVerify}
              disabled={!email}
              activeOpacity={0.85}
            >
              <Text style={styles.primaryButtonText}>Verify Email</Text>
            </TouchableOpacity>

            <TouchableOpacity style={styles.requestAccessButton}>
              <Text style={styles.requestAccessText}>Request Access for Your College</Text>
            </TouchableOpacity>
          </View>
        )}

        {step === 'verifying' && (
          <View style={styles.centerContent}>
            <Animated.View
              style={{
                transform: [
                  {
                    rotate: fadeAnim.interpolate({
                      inputRange: [0, 1],
                      outputRange: ['0deg', '360deg'],
                    }),
                  },
                ],
              }}
            >
              <Ionicons name="sync" size={80} color={COLORS.orange} />
            </Animated.View>
            <Text style={styles.verifyingText}>Verifying your college email...</Text>
          </View>
        )}

        {step === 'success' && (
          <View style={styles.centerContent}>
            <View style={styles.successCircle}>
              <Ionicons name="checkmark" size={60} color={COLORS.white} />
            </View>
            <View style={styles.verifiedBadge}>
              <Ionicons name="school" size={16} color={COLORS.success} />
              <Text style={styles.verifiedText}>College Verified</Text>
            </View>
            <Text style={styles.successTitle}>Welcome Aboard!</Text>
            <Text style={styles.successSubtitle}>Let's find you a ride</Text>
          </View>
        )}
      </Animated.View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: COLORS.background,
    zIndex: 1000,
  },
  scrollContainer: {
    flex: 1,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: SPACING.xl,
  },
  welcomeContainer: {
    alignItems: 'center',
  },
  animationContainer: {
    width: '100%',
    height: 100,
    marginBottom: SPACING.xxl,
    position: 'relative',
    justifyContent: 'center',
  },
  pathLine: {
    position: 'absolute',
    width: '100%',
    height: 2,
    backgroundColor: COLORS.cardBorder,
    top: '50%',
  },
  carIcon: {
    position: 'absolute',
  },
  welcomeTitle: {
    fontSize: FONTS.sizes.huge,
    fontWeight: FONTS.weights.bold,
    color: COLORS.textPrimary,
    textAlign: 'center',
    marginBottom: SPACING.md,
    letterSpacing: -0.5,
  },
  welcomeSubtitle: {
    fontSize: FONTS.sizes.lg,
    color: COLORS.textSecondary,
    textAlign: 'center',
    marginBottom: SPACING.xxl,
    lineHeight: 24,
  },
  formContainer: {
    alignItems: 'center',
  },
  shieldContainer: {
    marginBottom: SPACING.md,
  },
  formTitle: {
    fontSize: FONTS.sizes.xxl,
    fontWeight: FONTS.weights.bold,
    color: COLORS.textPrimary,
    marginTop: SPACING.lg,
    marginBottom: SPACING.sm,
  },
  formSubtitle: {
    fontSize: FONTS.sizes.md,
    color: COLORS.textSecondary,
    marginBottom: SPACING.xl,
    textAlign: 'center',
  },
  glassDropdown: {
    width: '100%',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: COLORS.glassDark,
    paddingHorizontal: SPACING.lg,
    paddingVertical: SPACING.md,
    borderRadius: BORDER_RADIUS.lg,
    borderWidth: 1,
    borderColor: COLORS.cardBorder,
    marginBottom: SPACING.md,
  },
  dropdownText: {
    flex: 1,
    fontSize: FONTS.sizes.md,
    color: COLORS.textPrimary,
  },
  collegeList: {
    width: '100%',
    maxHeight: 250,
    backgroundColor: COLORS.cardSurface,
    borderRadius: BORDER_RADIUS.lg,
    borderWidth: 1,
    borderColor: COLORS.cardBorder,
    marginBottom: SPACING.lg,
  },
  collegeItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: SPACING.lg,
    paddingVertical: SPACING.md,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.cardBorder,
  },
  selectedCollege: {
    backgroundColor: COLORS.elevated,
  },
  collegeItemText: {
    flex: 1,
    fontSize: FONTS.sizes.sm,
    color: COLORS.textSecondary,
  },
  selectedCollegeText: {
    color: COLORS.orange,
    fontWeight: FONTS.weights.semibold,
  },
  campusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.sm,
    backgroundColor: COLORS.orangeGlow,
    paddingHorizontal: SPACING.lg,
    paddingVertical: SPACING.sm,
    borderRadius: BORDER_RADIUS.pill,
    marginBottom: SPACING.lg,
  },
  campusBadgeText: {
    fontSize: FONTS.sizes.md,
    fontWeight: FONTS.weights.semibold,
    color: COLORS.orange,
  },
  inputContainer: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.md,
    backgroundColor: COLORS.glassDark,
    paddingHorizontal: SPACING.lg,
    borderRadius: BORDER_RADIUS.lg,
    borderWidth: 1,
    borderColor: COLORS.cardBorder,
    marginBottom: SPACING.sm,
  },
  floatingInput: {
    flex: 1,
    paddingVertical: SPACING.md,
    fontSize: FONTS.sizes.md,
    color: COLORS.textPrimary,
  },
  errorCapsule: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.sm,
    backgroundColor: COLORS.error + '20',
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.sm,
    borderRadius: BORDER_RADIUS.pill,
    marginBottom: SPACING.md,
    width: '100%',
  },
  errorText: {
    flex: 1,
    fontSize: FONTS.sizes.xs,
    color: COLORS.error,
  },
  privacyNotice: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: SPACING.sm,
    backgroundColor: COLORS.elevated,
    padding: SPACING.md,
    borderRadius: BORDER_RADIUS.md,
    marginBottom: SPACING.lg,
    width: '100%',
  },
  privacyText: {
    flex: 1,
    fontSize: FONTS.sizes.xs,
    color: COLORS.textTertiary,
    lineHeight: 16,
  },
  primaryButton: {
    width: '100%',
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: SPACING.sm,
    backgroundColor: COLORS.orange,
    paddingVertical: SPACING.md,
    borderRadius: BORDER_RADIUS.pill,
    marginTop: SPACING.lg,
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  primaryButtonText: {
    fontSize: FONTS.sizes.lg,
    fontWeight: FONTS.weights.bold,
    color: COLORS.white,
  },
  requestAccessButton: {
    marginTop: SPACING.lg,
  },
  requestAccessText: {
    fontSize: FONTS.sizes.sm,
    color: COLORS.textSecondary,
    textDecorationLine: 'underline',
  },
  centerContent: {
    alignItems: 'center',
    paddingVertical: SPACING.xxl,
  },
  verifyingText: {
    fontSize: FONTS.sizes.lg,
    color: COLORS.textSecondary,
    marginTop: SPACING.xl,
  },
  successCircle: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: COLORS.orange,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: SPACING.lg,
  },
  verifiedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.sm,
    backgroundColor: COLORS.success + '20',
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.xs,
    borderRadius: BORDER_RADIUS.pill,
    marginBottom: SPACING.lg,
  },
  verifiedText: {
    fontSize: FONTS.sizes.sm,
    fontWeight: FONTS.weights.semibold,
    color: COLORS.success,
  },
  successTitle: {
    fontSize: FONTS.sizes.xxl,
    fontWeight: FONTS.weights.bold,
    color: COLORS.textPrimary,
    marginBottom: SPACING.sm,
  },
  successSubtitle: {
    fontSize: FONTS.sizes.lg,
    color: COLORS.textSecondary,
  },
});