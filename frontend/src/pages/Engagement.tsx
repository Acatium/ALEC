import { useParams } from "react-router-dom";
import EngagementDashboard from "../components/EngagementDashboard";

export default function Engagement() {
  const { id } = useParams<{ id: string }>();
  if (!id) return <p>Missing engagement ID</p>;
  return <EngagementDashboard id={id} />;
}
