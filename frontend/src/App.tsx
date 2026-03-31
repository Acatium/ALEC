import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Home from "./pages/Home";
import Engagement from "./pages/Engagement";
import NewEngagementPage from "./pages/NewEngagement";
import ReportView from "./components/ReportView";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/engagements/new" element={<NewEngagementPage />} />
        <Route path="/engagements/:id" element={<Engagement />} />
        <Route path="/engagements/:id/report" element={<ReportView />} />
      </Routes>
    </Layout>
  );
}
