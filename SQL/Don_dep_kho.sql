
-- 1. Xóa bảng Staging
TRUNCATE TABLE Kho_du_lieu_staging.dbo.Stg_Price;
TRUNCATE TABLE Kho_du_lieu_staging.dbo.Stg_Ticker;

-- 2. Xóa bảng Fact trước (vì Fact giữ khóa ngoại của các Dim)
DELETE FROM DW_ChungKhoan.dbo.Fact_DailyPrice;

-- 3. Xóa các bảng Dim để SSIS nạp lại sạch sẽ
DELETE FROM DW_ChungKhoan.dbo.Dim_Stock;
DELETE FROM DW_ChungKhoan.dbo.Dim_Industry;
DELETE FROM DW_ChungKhoan.dbo.Dim_Date;

select * from Kho_du_lieu_staging.dbo.Stg_Price;