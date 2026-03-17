import { Outlet } from '@tanstack/react-router';
import { Layout } from '../components/Layout';

export default function RootLayout() {
  return (
    <Layout>
      <Outlet />
    </Layout>
  );
}
