export type AppEnv = {
  nexoraLearningBaseUrl: string;
  chatDBServerBaseUrl: string;
};

const DEFAULT_BASE_URL = "http://127.0.0.1:5001";
const DEFAULT_CHAT_BASE_URL = "http://127.0.0.1:5000";

export const appEnv: AppEnv = {
  nexoraLearningBaseUrl:
    process.env.EXPO_PUBLIC_NEXORA_LEARNING_BASE_URL || DEFAULT_BASE_URL,
  chatDBServerBaseUrl:
    process.env.EXPO_PUBLIC_CHAT_DB_SERVER_BASE_URL || DEFAULT_CHAT_BASE_URL,
};
