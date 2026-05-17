import { useNavigation, type CompositeNavigationProp } from "@react-navigation/native";
import type { BottomTabNavigationProp } from "@react-navigation/bottom-tabs";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { StyleSheet, View } from "react-native";

import { AppButton, AppCard, AppText, Screen, spacing } from "../../../design";
import type { MainTabParamList, RootStackParamList } from "../../../navigation/types";

type AdminNavigation = CompositeNavigationProp<
  BottomTabNavigationProp<MainTabParamList, "Admin">,
  NativeStackNavigationProp<RootStackParamList>
>;

export function AdminHomeScreen() {
  const navigation = useNavigation<AdminNavigation>();

  return (
    <Screen scroll>
      <AppText variant="title">内容管理</AppText>
      <AppCard style={styles.card}>
        <AppText tone="secondary">
          管理端切片应在学习者主路径稳定后实现，包括教材上传、提炼队列和向量化状态。
        </AppText>
      </AppCard>
      <View style={styles.actions}>
        <AppButton title="上传教材" onPress={() => navigation.navigate("BookUpload")} />
        <AppButton
          title="提炼队列"
          variant="secondary"
          onPress={() => navigation.navigate("RefinementQueue")}
        />
        <AppButton
          title="学习动态"
          variant="secondary"
          onPress={() => navigation.navigate("MainTabs", { screen: "Feed" })}
        />
        <AppButton
          title="向量化监控"
          variant="secondary"
          onPress={() => navigation.navigate("Vectorize")}
        />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.sm,
  },
  actions: {
    gap: spacing.sm,
  },
});
