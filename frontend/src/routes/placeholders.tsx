import { Placeholder } from "@/components/Placeholder";

export const BdmStudiesPage = () => (
  <Placeholder
    title="Catchment studies"
    subtitle="Requests you have raised and their progress"
    milestone="M3"
    body="Request a catchment study against a property or an analysed area and track it here."
  />
);

export const SmInboxPage = () => (
  <Placeholder
    title="Study requests"
    subtitle="Incoming catchment study requests"
    milestone="M3"
    body="New requests arrive here with a reuse check against existing studies, ready to split and assign."
  />
);

export const SmStudiesPage = () => (
  <Placeholder
    title="Studies in progress"
    subtitle="Progress by chunk and surveyor"
    milestone="M3"
    body="See which lanes are done, which drafts are waiting to sync, and who needs help."
  />
);

export const SeAssignmentsPage = () => (
  <Placeholder
    title="My assignments"
    subtitle="Lanes to survey, chunk by chunk"
    milestone="M3"
    body="Your assigned chunks will appear here and keep working offline once opened."
  />
);
