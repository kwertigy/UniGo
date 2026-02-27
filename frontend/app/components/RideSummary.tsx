import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  ScrollView,
} from 'react-native';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { GlassContainer } from './GlassContainer';
import { COLORS, SPACING, BORDER_RADIUS, FONTS } from '../constants/theme';

interface RideSummaryProps {
  visible: boolean;
  onClose: () => void;
  rideData: {
    ride_id: string;
    status: string;
    route: {
      origin: string;
      destination: string;
      distance_km?: number;
    };
    rider: {
      id: string;
      name: string;
    };
    driver: {
      id: string;
      name: string;
      rating?: number;
    };
    billing: {
      base_fare: number;
      service_fee: number;
      total_amount: number;
      payment_status: string;
    };
    eco_impact: {
      carbon_saved_kg: number;
    };
    timestamps: {
      created_at?: string;
      started_at?: string;
      completed_at?: string;
      duration_minutes?: number;
    };
  } | null;
}

export const RideSummary: React.FC<RideSummaryProps> = ({
  visible,
  onClose,
  rideData,
}) => {
  if (!rideData) return null;

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatCurrency = (amount: number) => {
    return `₹${amount.toLocaleString('en-IN')}`;
  };

  return (
    <Modal visible={visible} transparent animationType="slide">
      <View style={styles.overlay}>
        <GlassContainer style={styles.container}>
          <ScrollView showsVerticalScrollIndicator={false}>
            {/* Header */}
            <View style={styles.header}>
              <View style={styles.successIcon}>
                <Ionicons 
                  name={rideData.status === 'completed' ? 'checkmark-circle' : 'time'} 
                  size={48} 
                  color={rideData.status === 'completed' ? COLORS.emeraldGreen : COLORS.warning} 
                />
              </View>
              <Text style={styles.title}>
                {rideData.status === 'completed' ? 'Ride Completed!' : 'Ride Summary'}
              </Text>
              <Text style={styles.rideId}>Ride #{rideData.ride_id.slice(0, 8)}</Text>
            </View>

            {/* Route Section */}
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Route</Text>
              <View style={styles.routeContainer}>
                <View style={styles.routePoint}>
                  <Ionicons name="location" size={20} color={COLORS.emeraldGreen} />
                  <Text style={styles.routeText}>{rideData.route.origin}</Text>
                </View>
                <View style={styles.routeLine} />
                <View style={styles.routePoint}>
                  <Ionicons name="flag" size={20} color={COLORS.electricBlue} />
                  <Text style={styles.routeText}>{rideData.route.destination}</Text>
                </View>
              </View>
              {rideData.route.distance_km && (
                <Text style={styles.distanceText}>
                  Distance: {rideData.route.distance_km.toFixed(1)} km
                </Text>
              )}
            </View>

            {/* Driver Info */}
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Driver</Text>
              <View style={styles.driverCard}>
                <View style={styles.driverAvatar}>
                  <Ionicons name="person" size={24} color={COLORS.emeraldGreen} />
                </View>
                <View style={styles.driverInfo}>
                  <Text style={styles.driverName}>{rideData.driver.name}</Text>
                  {rideData.driver.rating && (
                    <View style={styles.ratingRow}>
                      <Ionicons name="star" size={14} color={COLORS.warning} />
                      <Text style={styles.ratingText}>{rideData.driver.rating.toFixed(1)}</Text>
                    </View>
                  )}
                </View>
              </View>
            </View>

            {/* Billing Section */}
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Billing</Text>
              <View style={styles.billingCard}>
                <View style={styles.billingRow}>
                  <Text style={styles.billingLabel}>Base Fare</Text>
                  <Text style={styles.billingValue}>{formatCurrency(rideData.billing.base_fare)}</Text>
                </View>
                <View style={styles.billingRow}>
                  <Text style={styles.billingLabel}>Service Fee</Text>
                  <Text style={styles.billingValue}>{formatCurrency(rideData.billing.service_fee)}</Text>
                </View>
                <View style={styles.divider} />
                <View style={styles.billingRow}>
                  <Text style={styles.totalLabel}>Total</Text>
                  <Text style={styles.totalValue}>{formatCurrency(rideData.billing.total_amount)}</Text>
                </View>
                <View style={styles.paymentStatus}>
                  <Ionicons 
                    name={rideData.billing.payment_status === 'captured' ? 'checkmark-circle' : 'time-outline'} 
                    size={16} 
                    color={rideData.billing.payment_status === 'captured' ? COLORS.emeraldGreen : COLORS.warning} 
                  />
                  <Text style={[
                    styles.paymentStatusText,
                    { color: rideData.billing.payment_status === 'captured' ? COLORS.emeraldGreen : COLORS.warning }
                  ]}>
                    {rideData.billing.payment_status === 'captured' ? 'Payment Complete' : 'Payment Pending'}
                  </Text>
                </View>
              </View>
            </View>

            {/* Eco Impact */}
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Eco Impact</Text>
              <View style={styles.ecoCard}>
                <MaterialCommunityIcons name="leaf" size={32} color={COLORS.emeraldGreen} />
                <View style={styles.ecoInfo}>
                  <Text style={styles.ecoValue}>{rideData.eco_impact.carbon_saved_kg.toFixed(1)} kg</Text>
                  <Text style={styles.ecoLabel}>CO₂ Saved by carpooling</Text>
                </View>
              </View>
            </View>

            {/* Timestamps */}
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Trip Details</Text>
              <View style={styles.timestampCard}>
                {rideData.timestamps.started_at && (
                  <View style={styles.timestampRow}>
                    <Text style={styles.timestampLabel}>Started</Text>
                    <Text style={styles.timestampValue}>{formatDate(rideData.timestamps.started_at)}</Text>
                  </View>
                )}
                {rideData.timestamps.completed_at && (
                  <View style={styles.timestampRow}>
                    <Text style={styles.timestampLabel}>Completed</Text>
                    <Text style={styles.timestampValue}>{formatDate(rideData.timestamps.completed_at)}</Text>
                  </View>
                )}
                {rideData.timestamps.duration_minutes && (
                  <View style={styles.timestampRow}>
                    <Text style={styles.timestampLabel}>Duration</Text>
                    <Text style={styles.timestampValue}>{rideData.timestamps.duration_minutes} minutes</Text>
                  </View>
                )}
              </View>
            </View>

            {/* Close Button */}
            <TouchableOpacity style={styles.closeButton} onPress={onClose}>
              <Text style={styles.closeButtonText}>Done</Text>
            </TouchableOpacity>
          </ScrollView>
        </GlassContainer>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: SPACING.md,
  },
  container: {
    width: '100%',
    maxWidth: 400,
    maxHeight: '90%',
    padding: SPACING.lg,
  },
  header: {
    alignItems: 'center',
    marginBottom: SPACING.xl,
  },
  successIcon: {
    marginBottom: SPACING.md,
  },
  title: {
    fontSize: FONTS.sizes.xl,
    fontWeight: 'bold',
    color: COLORS.white,
    marginBottom: SPACING.xs,
  },
  rideId: {
    fontSize: FONTS.sizes.sm,
    color: COLORS.whiteAlpha60,
  },
  section: {
    marginBottom: SPACING.lg,
  },
  sectionTitle: {
    fontSize: FONTS.sizes.md,
    fontWeight: '600',
    color: COLORS.whiteAlpha80,
    marginBottom: SPACING.sm,
  },
  routeContainer: {
    backgroundColor: COLORS.slate800,
    borderRadius: BORDER_RADIUS.md,
    padding: SPACING.md,
  },
  routePoint: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.sm,
  },
  routeLine: {
    width: 2,
    height: 20,
    backgroundColor: COLORS.slate700,
    marginLeft: 9,
    marginVertical: SPACING.xs,
  },
  routeText: {
    fontSize: FONTS.sizes.md,
    color: COLORS.white,
    flex: 1,
  },
  distanceText: {
    fontSize: FONTS.sizes.sm,
    color: COLORS.whiteAlpha60,
    marginTop: SPACING.sm,
    textAlign: 'center',
  },
  driverCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.slate800,
    borderRadius: BORDER_RADIUS.md,
    padding: SPACING.md,
  },
  driverAvatar: {
    width: 48,
    height: 48,
    borderRadius: BORDER_RADIUS.full,
    backgroundColor: COLORS.slate700,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: SPACING.md,
  },
  driverInfo: {
    flex: 1,
  },
  driverName: {
    fontSize: FONTS.sizes.md,
    fontWeight: '600',
    color: COLORS.white,
  },
  ratingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.xs,
    marginTop: SPACING.xs,
  },
  ratingText: {
    fontSize: FONTS.sizes.sm,
    color: COLORS.warning,
  },
  billingCard: {
    backgroundColor: COLORS.slate800,
    borderRadius: BORDER_RADIUS.md,
    padding: SPACING.md,
  },
  billingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.sm,
  },
  billingLabel: {
    fontSize: FONTS.sizes.md,
    color: COLORS.whiteAlpha80,
  },
  billingValue: {
    fontSize: FONTS.sizes.md,
    color: COLORS.white,
  },
  divider: {
    height: 1,
    backgroundColor: COLORS.slate700,
    marginVertical: SPACING.sm,
  },
  totalLabel: {
    fontSize: FONTS.sizes.lg,
    fontWeight: 'bold',
    color: COLORS.white,
  },
  totalValue: {
    fontSize: FONTS.sizes.lg,
    fontWeight: 'bold',
    color: COLORS.emeraldGreen,
  },
  paymentStatus: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: SPACING.xs,
    marginTop: SPACING.md,
    paddingTop: SPACING.sm,
    borderTopWidth: 1,
    borderTopColor: COLORS.slate700,
  },
  paymentStatusText: {
    fontSize: FONTS.sizes.sm,
    fontWeight: '600',
  },
  ecoCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.emeraldGreen + '20',
    borderRadius: BORDER_RADIUS.md,
    padding: SPACING.md,
    borderWidth: 1,
    borderColor: COLORS.emeraldGreen + '40',
  },
  ecoInfo: {
    marginLeft: SPACING.md,
    flex: 1,
  },
  ecoValue: {
    fontSize: FONTS.sizes.xl,
    fontWeight: 'bold',
    color: COLORS.emeraldGreen,
  },
  ecoLabel: {
    fontSize: FONTS.sizes.sm,
    color: COLORS.whiteAlpha80,
  },
  timestampCard: {
    backgroundColor: COLORS.slate800,
    borderRadius: BORDER_RADIUS.md,
    padding: SPACING.md,
  },
  timestampRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: SPACING.sm,
  },
  timestampLabel: {
    fontSize: FONTS.sizes.sm,
    color: COLORS.whiteAlpha60,
  },
  timestampValue: {
    fontSize: FONTS.sizes.sm,
    color: COLORS.white,
  },
  closeButton: {
    backgroundColor: COLORS.emeraldGreen,
    padding: SPACING.md,
    borderRadius: BORDER_RADIUS.md,
    alignItems: 'center',
    marginTop: SPACING.md,
  },
  closeButtonText: {
    fontSize: FONTS.sizes.md,
    fontWeight: 'bold',
    color: COLORS.white,
  },
});
