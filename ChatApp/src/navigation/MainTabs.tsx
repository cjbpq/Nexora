import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";

import { useSession } from "../app/providers/SessionProvider";
import { AdminHomeScreen } from "../features/admin/screens/AdminHomeScreen";
import { ConversationScreen } from "../features/chat/screens/ConversationScreen";
import { CourseListScreen } from "../features/courses/screens/CourseListScreen";
import { DashboardScreen } from "../features/dashboard/screens/DashboardScreen";
import { LearningFeedScreen } from "../features/feed/screens/LearningFeedScreen";
import { SettingsScreen } from "../features/settings/screens/SettingsScreen";
import type { MainTabParamList } from "./types";

const Tab = createBottomTabNavigator<MainTabParamList>();

export function MainTabs() {
  const { isAdmin } = useSession();

  return (
    <Tab.Navigator>
      <Tab.Screen name="Dashboard" component={DashboardScreen} options={{ title: "学习" }} />
      <Tab.Screen name="Courses" component={CourseListScreen} options={{ title: "课程" }} />
      <Tab.Screen name="Feed" component={LearningFeedScreen} options={{ title: "动态" }} />
      <Tab.Screen name="Chat" component={ConversationScreen} options={{ title: "问答" }} />
      {isAdmin ? (
        <Tab.Screen name="Admin" component={AdminHomeScreen} options={{ title: "管理" }} />
      ) : null}
      <Tab.Screen name="Settings" component={SettingsScreen} options={{ title: "设置" }} />
    </Tab.Navigator>
  );
}
