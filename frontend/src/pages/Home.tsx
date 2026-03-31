import { Link } from "react-router-dom";
import EngagementList from "../components/EngagementList";

export default function Home() {
  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Engagements</h1>
        <Link
          to="/engagements/new"
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700"
        >
          New Engagement
        </Link>
      </div>
      <EngagementList />
    </div>
  );
}
