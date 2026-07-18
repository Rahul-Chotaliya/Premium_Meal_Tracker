import React, { useState, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

const ALLOWED_TAGS = ['vegetarian', 'non-vegetarian', 'vegan', 'high-protein', 'low-carb', 'snack'];
const DEFAULT_DATE = '2026-06-12'; // Defaulting to seed data date on initial load

export default function App() {
  // Filters & State
  const [activeDate, setActiveDate] = useState(DEFAULT_DATE);
  const [activeTag, setActiveTag] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);

  // Data Fetches
  const [mealsData, setMealsData] = useState({ results: [], count: 0, next: null, previous: null });
  const [summaryData, setSummaryData] = useState(null);
  const [trendsData, setTrendsData] = useState(null);

  // UI Status
  const [loading, setLoading] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [globalError, setGlobalError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});

  // Add Meal Form
  const [formMode, setFormMode] = useState('manual'); // 'manual' or 'ai'
  const [formValues, setFormValues] = useState({
    name: '',
    calories: '',
    protein_g: '',
    carbs_g: '',
    fat_g: '',
    tags: [],
    eaten_at: new Date().toISOString().substring(0, 16) // YYYY-MM-DDTHH:MM
  });
  const [aiText, setAiText] = useState('');

  // Fetch all dashboard data when filters change
  useEffect(() => {
    fetchDashboardData();
  }, [activeDate, activeTag, searchQuery, page]);

  const fetchDashboardData = async () => {
    setLoading(true);
    setGlobalError('');
    try {
      await Promise.all([
        fetchMeals(),
        fetchSummary(),
        fetchTrends()
      ]);
    } catch (err) {
      setGlobalError('Connection failed. Make sure the backend service is running.');
    } finally {
      setLoading(false);
    }
  };

  const fetchMeals = async () => {
    let url = `${API_BASE}/api/meals/?page=${page}`;
    if (activeDate) url += `&date=${activeDate}`;
    if (activeTag) url += `&tag=${activeTag}`;
    if (searchQuery) url += `&search=${encodeURIComponent(searchQuery)}`;

    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to fetch meals');
    const data = await res.json();
    setMealsData(data);
  };

  const fetchSummary = async () => {
    if (!activeDate) return;
    const res = await fetch(`${API_BASE}/api/meals/summary/?date=${activeDate}`);
    if (!res.ok) throw new Error('Failed to fetch summary');
    const data = await res.json();
    setSummaryData(data);
  };

  const fetchTrends = async () => {
    const res = await fetch(`${API_BASE}/api/meals/trends/?days=7`);
    if (!res.ok) throw new Error('Failed to fetch trends');
    const data = await res.json();
    setTrendsData(data);
  };

  // Local Form Validation
  const validateForm = () => {
    const errors = {};
    if (!formValues.name.trim()) {
      errors.name = 'Meal name is required.';
    } else if (formValues.name.length > 100) {
      errors.name = 'Name must be under 100 characters.';
    }

    const cals = parseInt(formValues.calories);
    if (isNaN(cals) || cals < 1 || cals > 5000) {
      errors.calories = 'Calories must be between 1 and 5,000 kcal.';
    }

    const pro = parseInt(formValues.protein_g);
    if (isNaN(pro) || pro < 0 || pro > 500) {
      errors.protein_g = 'Protein must be between 0 and 500g.';
    }

    const carb = parseInt(formValues.carbs_g);
    if (isNaN(carb) || carb < 0 || carb > 500) {
      errors.carbs_g = 'Carbs must be between 0 and 500g.';
    }

    const fat = parseInt(formValues.fat_g);
    if (isNaN(fat) || fat < 0 || fat > 500) {
      errors.fat_g = 'Fat must be between 0 and 500g.';
    }

    if (!formValues.eaten_at) {
      errors.eaten_at = 'Date and time are required.';
    } else {
      const selectedTime = new Date(formValues.eaten_at);
      if (selectedTime > new Date()) {
        errors.eaten_at = 'Log time cannot be in the future.';
      }
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  // Handle Form Input Changes
  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormValues(prev => ({ ...prev, [name]: value }));
  };

  // Toggle Tags Multiselect
  const handleTagToggle = (tag) => {
    setFormValues(prev => {
      const tags = prev.tags.includes(tag)
        ? prev.tags.filter(t => t !== tag)
        : [...prev.tags, tag];
      return { ...prev, tags };
    });
  };

  // Create Manual Meal
  const handleAddMeal = async (e) => {
    e.preventDefault();
    if (!validateForm()) return;

    setSubmitLoading(true);
    setGlobalError('');
    setFieldErrors({});

    try {
      const payload = {
        ...formValues,
        calories: parseInt(formValues.calories),
        protein_g: parseInt(formValues.protein_g),
        carbs_g: parseInt(formValues.carbs_g),
        fat_g: parseInt(formValues.fat_g),
        eaten_at: new Date(formValues.eaten_at).toISOString() // Convert to UTC ISO
      };

      const res = await fetch(`${API_BASE}/api/meals/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.status === 409) {
        setGlobalError('Duplicate Meal: A meal with this name was already logged within ±30 minutes.');
        return;
      }

      if (res.status === 400) {
        const errData = await res.json();
        setFieldErrors(errData);
        return;
      }

      if (!res.ok) throw new Error('Submission failed');

      // Reset form and refresh
      setFormValues({
        name: '',
        calories: '',
        protein_g: '',
        carbs_g: '',
        fat_g: '',
        tags: [],
        eaten_at: new Date().toISOString().substring(0, 16)
      });
      fetchDashboardData();
    } catch (err) {
      setGlobalError('Failed to add meal. Check API connection.');
    } finally {
      setSubmitLoading(false);
    }
  };

  // Create AI Quick-Add Meal
  const handleQuickAdd = async (e) => {
    e.preventDefault();
    if (!aiText.trim()) return;

    setSubmitLoading(true);
    setGlobalError('');

    try {
      const res = await fetch(`${API_BASE}/api/meals/quick-add/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: aiText })
      });

      if (res.status === 422) {
        const data = await res.json();
        setGlobalError(data.error || 'AI parsing failed. Please format the entry clearly.');
        return;
      }

      if (!res.ok) throw new Error('AI parse error');

      setAiText('');
      fetchDashboardData();
    } catch (err) {
      setGlobalError('AI quick-add failed. Make sure LLM keys are configured on your backend.');
    } finally {
      setSubmitLoading(false);
    }
  };

  // Delete Meal
  const handleDeleteMeal = async (id) => {
    if (!confirm('Are you sure you want to delete this meal log?')) return;
    setSubmitLoading(true);
    setGlobalError('');

    try {
      const res = await fetch(`${API_BASE}/api/meals/${id}/`, {
        method: 'DELETE'
      });

      if (!res.ok) throw new Error('Deletion failed');

      fetchDashboardData();
    } catch (err) {
      setGlobalError('Failed to delete meal. Please check server connections.');
    } finally {
      setSubmitLoading(false);
    }
  };

  // Reset all filters
  const handleClearFilters = () => {
    setActiveDate(DEFAULT_DATE);
    setActiveTag('');
    setSearchQuery('');
    setPage(1);
  };

  // SVG Chart Dimensions
  const chartW = 600;
  const chartH = 200;
  const paddingX = 40;
  const paddingY = 25;
  const goalLineVal = 2000;

  return (
    <div className="app-container">
      <header>
        <div>
          <h1>Plate<span className="logo-dot">.</span></h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginTop: '0.25rem' }}>
            Premium Daily Meal Tracker & Macro Dashboard
          </p>
        </div>
        {loading && <div className="loading-spinner" />}
      </header>

      {/* Global Error Banner */}
      {globalError && (
        <div className="error-block">
          <span>{globalError}</span>
          <button style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontWeight: 'bold' }} onClick={() => setGlobalError('')}>✕</button>
        </div>
      )}

      {/* Main Section */}
      <div className="dashboard-grid">
        {/* Left Side: Logger Form Card */}
        <aside className="left-panel">
          <div className="card">
            <div className="toggle-tab-container">
              <div 
                className={`toggle-tab ${formMode === 'manual' ? 'active' : ''}`}
                onClick={() => setFormMode('manual')}
              >
                Manual Log
              </div>
              <div 
                className={`toggle-tab ${formMode === 'ai' ? 'active' : ''}`}
                onClick={() => setFormMode('ai')}
              >
                AI Quick-Add
              </div>
            </div>

            {formMode === 'manual' ? (
              <form onSubmit={handleAddMeal}>
                <div className="form-group">
                  <label htmlFor="name">Meal Name</label>
                  <input
                    type="text"
                    id="name"
                    name="name"
                    className="form-control"
                    placeholder="e.g., Paneer Tikka Salad"
                    value={formValues.name}
                    onChange={handleInputChange}
                    disabled={submitLoading}
                  />
                  {fieldErrors.name && <span className="form-error">{fieldErrors.name}</span>}
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="calories">Calories (kcal)</label>
                    <input
                      type="number"
                      id="calories"
                      name="calories"
                      className="form-control"
                      placeholder="320"
                      value={formValues.calories}
                      onChange={handleInputChange}
                      disabled={submitLoading}
                    />
                    {fieldErrors.calories && <span className="form-error">{fieldErrors.calories}</span>}
                  </div>
                  <div className="form-group">
                    <label htmlFor="eaten_at">Log Time</label>
                    <input
                      type="datetime-local"
                      id="eaten_at"
                      name="eaten_at"
                      className="form-control"
                      value={formValues.eaten_at}
                      onChange={handleInputChange}
                      disabled={submitLoading}
                    />
                    {fieldErrors.eaten_at && <span className="form-error">{fieldErrors.eaten_at}</span>}
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="protein_g">Protein (g)</label>
                    <input
                      type="number"
                      id="protein_g"
                      name="protein_g"
                      className="form-control"
                      placeholder="24"
                      value={formValues.protein_g}
                      onChange={handleInputChange}
                      disabled={submitLoading}
                    />
                    {fieldErrors.protein_g && <span className="form-error">{fieldErrors.protein_g}</span>}
                  </div>
                  <div className="form-group">
                    <label htmlFor="carbs_g">Carbs (g)</label>
                    <input
                      type="number"
                      id="carbs_g"
                      name="carbs_g"
                      className="form-control"
                      placeholder="12"
                      value={formValues.carbs_g}
                      onChange={handleInputChange}
                      disabled={submitLoading}
                    />
                    {fieldErrors.carbs_g && <span className="form-error">{fieldErrors.carbs_g}</span>}
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor="fat_g">Fat (g)</label>
                  <input
                    type="number"
                    id="fat_g"
                    name="fat_g"
                    className="form-control"
                    placeholder="18"
                    value={formValues.fat_g}
                    onChange={handleInputChange}
                    disabled={submitLoading}
                  />
                  {fieldErrors.fat_g && <span className="form-error">{fieldErrors.fat_g}</span>}
                </div>

                <div className="form-group">
                  <label>Tags</label>
                  <div className="tag-select-container">
                    {ALLOWED_TAGS.map(tag => (
                      <span
                        key={tag}
                        className={`tag-option ${formValues.tags.includes(tag) ? 'selected' : ''}`}
                        onClick={() => handleTagToggle(tag)}
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                  {fieldErrors.tags && <span className="form-error">{fieldErrors.tags}</span>}
                </div>

                <button type="submit" className="btn btn-primary" disabled={submitLoading}>
                  {submitLoading ? 'Saving...' : 'Add Meal Entry'}
                </button>
              </form>
            ) : (
              <form onSubmit={handleQuickAdd}>
                <div className="form-group">
                  <label htmlFor="aiText">Describe what you ate</label>
                  <textarea
                    id="aiText"
                    rows="6"
                    className="form-control"
                    placeholder="e.g. 2 rotis, a bowl of dal makhani and one protein shake"
                    value={aiText}
                    onChange={(e) => setAiText(e.target.value)}
                    disabled={submitLoading}
                    style={{ resize: 'none' }}
                  />
                </div>
                <button type="submit" className="btn btn-primary" disabled={submitLoading || !aiText.trim()}>
                  {submitLoading ? 'Parsing...' : 'AI Quick Log'}
                </button>
              </form>
            )}
          </div>
        </aside>

        {/* Right Side: Metrics Dashboard and Meals List */}
        <main className="main-panel">
          
          {/* Summary Dashboard Card */}
          {summaryData && (
            <div className="card">
              <div className="card-title">
                <span>Daily Breakdown</span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 'normal' }}>
                  Date: {summaryData.date}
                </span>
              </div>
              <div className="summary-bar">
                {/* Calories Progress Meter */}
                <div className="progress-container">
                  <div className="progress-header">
                    <span style={{ fontWeight: '500' }}>Calorie Intake Progress</span>
                    <span style={{ color: summaryData.total_calories > summaryData.goal_kcal ? 'var(--color-danger)' : 'var(--color-success)' }}>
                      {summaryData.total_calories} / {summaryData.goal_kcal} kcal
                    </span>
                  </div>
                  <div className="progress-track">
                    <div 
                      className={`progress-bar ${summaryData.total_calories > summaryData.goal_kcal ? 'over' : 'under'}`}
                      style={{ width: `${Math.min(100, (summaryData.total_calories / summaryData.goal_kcal) * 100)}%` }}
                    />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    <span>Remaining: {summaryData.remaining_kcal} kcal</span>
                    <span>Meal Count: {summaryData.meal_count}</span>
                  </div>
                </div>

                {/* Macro Summary Metrics */}
                <div className="metric-card">
                  <span className="metric-label">Macronutrients</span>
                  <div className="macro-split">
                    <div className="macro-badge protein">
                      <span className="dot" />
                      <span>{summaryData.macros.protein_g}g Pro</span>
                    </div>
                    <div className="macro-badge carbs">
                      <span className="dot" />
                      <span>{summaryData.macros.carbs_g}g Carb</span>
                    </div>
                    <div className="macro-badge fat">
                      <span className="dot" />
                      <span>{summaryData.macros.fat_g}g Fat</span>
                    </div>
                  </div>
                </div>

                {/* Top Tags Metric */}
                <div className="metric-card">
                  <span className="metric-label">Top Tag(s)</span>
                  <div className="meal-tags" style={{ marginTop: '0.25rem' }}>
                    {summaryData.top_tags.length > 0 ? (
                      summaryData.top_tags.map(tag => (
                        <span key={tag} className="tag-badge" style={{ borderColor: 'var(--accent-purple)' }}>{tag}</span>
                      ))
                    ) : (
                      <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>None logged</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* SVG Trends Bar Chart */}
          {trendsData && trendsData.series && (
            <div className="card">
              <div className="card-title">7-Day Calorie Trends</div>
              <div className="chart-container">
                <svg className="svg-chart" viewBox={`0 0 ${chartW} ${chartH}`} width="100%">
                  {/* Drawing background gridlines */}
                  {[0.25, 0.5, 0.75, 1].map((scale, idx) => {
                    const gridY = paddingY + (chartH - 2 * paddingY) * (1 - scale);
                    return (
                      <g key={idx}>
                        <line 
                          x1={paddingX} 
                          y1={gridY} 
                          x2={chartW - paddingX} 
                          y2={gridY} 
                          stroke="rgba(255,255,255,0.04)" 
                          strokeWidth="1"
                        />
                        <text 
                          x={paddingX - 10} 
                          y={gridY + 4} 
                          fill="var(--text-secondary)" 
                          fontSize="9" 
                          textAnchor="end"
                        >
                          {Math.round(goalLineVal * scale)}
                        </text>
                      </g>
                    );
                  })}

                  {/* Render bars */}
                  {trendsData.series.map((day, idx) => {
                    const daysLen = trendsData.series.length;
                    const barSpace = (chartW - 2 * paddingX) / daysLen;
                    const barWidth = barSpace - 16;
                    const barX = paddingX + idx * barSpace + 8;
                    
                    // Scale height relative to goal line 2000
                    const maxVal = Math.max(...trendsData.series.map(d => d.calories), goalLineVal);
                    const usableHeight = chartH - 2 * paddingY;
                    const barHeight = (day.calories / maxVal) * usableHeight;
                    const barY = chartH - paddingY - barHeight;

                    const isSelected = day.date === activeDate;
                    const isOver = day.calories > goalLineVal;

                    return (
                      <g key={day.date}>
                        {/* Hover Tooltip/Title */}
                        <title>{`${day.date}\nCalories: ${day.calories} kcal`}</title>
                        <rect
                          x={barX}
                          y={barY}
                          width={barWidth}
                          height={Math.max(2, barHeight)} // Minimal 2px visible line
                          rx="4"
                          ry="4"
                          fill={isOver ? 'var(--color-danger)' : 'var(--accent-purple)'}
                          opacity={isSelected ? 1.0 : 0.6}
                          className={`bar-rect ${isSelected ? 'selected' : ''}`}
                          onClick={() => {
                            setActiveDate(day.date);
                            setPage(1);
                          }}
                        />
                        {/* Date under graph */}
                        <text
                          x={barX + barWidth / 2}
                          y={chartH - paddingY + 16}
                          fill={isSelected ? '#fff' : 'var(--text-secondary)'}
                          fontSize="9"
                          textAnchor="middle"
                          fontWeight={isSelected ? 'bold' : 'normal'}
                        >
                          {day.date.substring(5)} {/* Show MM-DD */}
                        </text>
                      </g>
                    );
                  })}
                </svg>
                
                {/* Trends Side Statistics */}
                <div className="trends-header-summary">
                  <div className="trends-metric">
                    <div className="trends-metric-label">Avg Daily</div>
                    <div className="trends-metric-value">{trendsData.avg_daily_kcal} kcal</div>
                  </div>
                  <div className="trends-metric">
                    <div className="trends-metric-label">Best Day</div>
                    <div className="trends-metric-value" style={{ color: 'var(--color-success)' }}>
                      {trendsData.best_day.calories > 0 ? `${trendsData.best_day.calories} kcal` : 'N/A'}
                    </div>
                  </div>
                  <div className="trends-metric">
                    <div className="trends-metric-label">Days Over Goal</div>
                    <div className="trends-metric-value" style={{ color: trendsData.days_over_goal > 0 ? 'var(--color-danger)' : 'inherit' }}>
                      {trendsData.days_over_goal}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Filters and List */}
          <div className="card">
            <div className="card-title">
              <span>Logged Meals</span>
              <button 
                style={{ fontSize: '0.8rem', background: 'none', border: 'none', color: 'var(--accent-purple)', cursor: 'pointer' }}
                onClick={handleClearFilters}
              >
                Clear Filters
              </button>
            </div>

            {/* Combined Filters */}
            <div className="filters-bar">
              <div className="filter-item">
                <label htmlFor="filter-date">Log Date</label>
                <input
                  type="date"
                  id="filter-date"
                  className="form-control"
                  value={activeDate}
                  onChange={(e) => {
                    setActiveDate(e.target.value);
                    setPage(1);
                  }}
                />
              </div>

              <div className="filter-item">
                <label htmlFor="filter-tag">Tag</label>
                <select
                  id="filter-tag"
                  className="form-control"
                  value={activeTag}
                  onChange={(e) => {
                    setActiveTag(e.target.value);
                    setPage(1);
                  }}
                >
                  <option value="">All Tags</option>
                  {ALLOWED_TAGS.map(tag => (
                    <option key={tag} value={tag}>{tag}</option>
                  ))}
                </select>
              </div>

              <div className="filter-item">
                <label htmlFor="filter-search">Search Name</label>
                <input
                  type="text"
                  id="filter-search"
                  className="form-control"
                  placeholder="Search meal name..."
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setPage(1);
                  }}
                />
              </div>
            </div>

            {/* Meals List / Empty Blocks */}
            {mealsData.results.length > 0 ? (
              <div className="meals-list">
                {mealsData.results.map(meal => (
                  <div key={meal.id} className="meal-card">
                    <div className="meal-info">
                      <div className="meal-name-row">
                        <span className="meal-name">{meal.name}</span>
                        <span className={`meal-source-badge ${meal.source}`}>
                          {meal.source}
                        </span>
                      </div>
                      <div className="meal-meta">
                        <span>Eaten at: {new Date(meal.eaten_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      </div>
                      <div className="meal-tags">
                        {meal.tags.map(tag => (
                          <span key={tag} className="tag-badge">{tag}</span>
                        ))}
                      </div>
                    </div>

                    <div className="meal-stats">
                      <div className="meal-calories">
                        <div className="meal-kcal-val">{meal.calories}</div>
                        <div className="meal-macros-summary">
                          {meal.protein_g}P / {meal.carbs_g}C / {meal.fat_g}F
                        </div>
                      </div>
                      <button 
                        className="btn-delete" 
                        onClick={() => handleDeleteMeal(meal.id)}
                        disabled={submitLoading}
                        title="Delete meal log"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                ))}

                {/* Pagination Controls */}
                {(mealsData.next || mealsData.previous) && (
                  <div className="pagination-container">
                    <button 
                      className="btn-nav"
                      onClick={() => setPage(prev => Math.max(1, prev - 1))}
                      disabled={!mealsData.previous || loading}
                    >
                      ← Previous
                    </button>
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Page {page}</span>
                    <button 
                      className="btn-nav"
                      onClick={() => setPage(prev => prev + 1)}
                      disabled={!mealsData.next || loading}
                    >
                      Next →
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="empty-block">
                <p>No meals logged matching current criteria.</p>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
                  Try choosing a different date filter or search term.
                </p>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
