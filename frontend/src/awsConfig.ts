import { Amplify } from "aws-amplify";

const region = import.meta.env.VITE_AWS_REGION;
const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID;
const userPoolClientId = import.meta.env.VITE_COGNITO_USER_POOL_CLIENT_ID;

export const amplifyConfigured = Boolean(region && userPoolId && userPoolClientId);

if (amplifyConfigured) {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId,
        userPoolClientId,
        signUpVerificationMethod: "code",
        loginWith: {
          email: true
        }
      }
    }
  });
}
