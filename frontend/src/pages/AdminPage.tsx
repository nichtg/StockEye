import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { ProviderBanner } from '../features/admin/ProviderBanner';
import { ProvidersSection } from '../features/admin/ProvidersSection';
import { UsersSection } from '../features/admin/UsersSection';
import { useDocumentTitle } from '../hooks';
import { layout } from '../theme/tokens';

/** Role gating happens in the route (see App.tsx) so non-admins never even download this chunk. */
export default function AdminPage() {
  useDocumentTitle('Admin');
  return (
    <Box>
      <Typography variant="h1" sx={{ mb: 3 }}>
        Admin
      </Typography>
      <ProviderBanner />
      <ProvidersSection />
      <Box sx={{ mt: layout.sectionGap }}>
        <UsersSection />
      </Box>
    </Box>
  );
}
